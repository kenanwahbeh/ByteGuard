import http.client
import json
import threading
import unittest

from byteguard.errors import ByteGuardError
from byteguard.manager import Manager
from byteguard.web import auth, server
from fakes import FakeRun, temp_paths

PASSWORD = "correct horse"
UFW_ACTIVE = {"ufw status": "Status: active\n"}


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class PasswordTest(unittest.TestCase):
    def test_the_right_password_verifies_and_a_wrong_one_does_not(self):
        stored = auth.hash_password(PASSWORD)

        self.assertTrue(auth.verify_password(PASSWORD, stored))
        self.assertFalse(auth.verify_password("correct horse ", stored))

    def test_the_password_itself_is_never_stored(self):
        self.assertNotIn(PASSWORD, json.dumps(auth.hash_password(PASSWORD)))

    def test_the_same_password_hashes_differently_each_time(self):
        self.assertNotEqual(auth.hash_password(PASSWORD)["hash"], auth.hash_password(PASSWORD)["hash"])


class SessionsTest(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.sessions = auth.Sessions(self.clock)

    def test_a_session_is_valid_until_it_expires(self):
        token = self.sessions.start()
        self.assertTrue(self.sessions.valid(token))

        self.clock.now += auth.SESSION_SECONDS + 1

        self.assertFalse(self.sessions.valid(token))

    def test_unknown_and_ended_sessions_are_not_valid(self):
        token = self.sessions.start()
        self.sessions.end(token)

        for candidate in (token, "made-up", "", None):
            self.assertFalse(self.sessions.valid(candidate))

    def test_repeated_failures_lock_logins_until_the_window_passes(self):
        for _ in range(auth.MAX_FAILURES):
            self.assertFalse(self.sessions.locked_out("198.51.100.9"))
            self.sessions.record_failure("198.51.100.9")
        self.assertTrue(self.sessions.locked_out("198.51.100.9"))

        self.clock.now += auth.FAILURE_WINDOW_SECONDS + 1

        self.assertFalse(self.sessions.locked_out("198.51.100.9"))

    def test_one_clients_failures_never_lock_out_another(self):
        for _ in range(auth.MAX_FAILURES):
            self.sessions.record_failure("198.51.100.9")

        self.assertFalse(self.sessions.locked_out("203.0.113.50"))


class WebTestCase(unittest.TestCase):
    def setUp(self):
        self.manager = Manager(
            temp_paths(self),
            FakeRun(outputs={"qrencode -t SVG -o -": "<svg/>", **UFW_ACTIVE}),
        )
        self.manager.set_up(iface="eth0", endpoint="203.0.113.7", port=51820)
        self.manager.enable_ui(PASSWORD)
        self.httpd = server.make_server(server.App(self.manager), "127.0.0.1", 0)
        thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join)
        self.addCleanup(self.httpd.server_close)
        self.addCleanup(self.httpd.shutdown)
        self.cookie = None

    def request(self, method, path, body=None, *, csrf=True, cookie=True, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.httpd.server_address[1], timeout=10)
        headers = dict(headers or {})
        if csrf:
            headers["X-ByteGuard"] = "1"
        if cookie and self.cookie:
            headers["Cookie"] = self.cookie
        connection.request(method, path, json.dumps(body) if body is not None else None, headers)
        response = connection.getresponse()
        raw = response.read()
        connection.close()
        is_json = response.headers["Content-Type"].startswith("application/json")
        return response, (json.loads(raw) if is_json else raw.decode())

    def login(self):
        response, _ = self.request("POST", "/api/login", {"password": PASSWORD})
        self.cookie = response.headers["Set-Cookie"].split(";")[0]
        return response


class LoginTest(WebTestCase):
    def test_nothing_is_readable_without_signing_in(self):
        for method, path in (("GET", "/api/state"), ("GET", "/api/devices/phone"), ("GET", "/api/backup/download"),
                             ("POST", "/api/devices"), ("DELETE", "/api/devices/phone")):
            response, body = self.request(method, path, {} if method == "POST" else None)
            self.assertEqual((response.status, body), (401, {"error": "login"}), path)

    def test_a_wrong_password_is_refused(self):
        response, body = self.request("POST", "/api/login", {"password": "wrong"})

        self.assertEqual((response.status, body["error"]), (401, "password"))
        self.assertIsNone(response.headers["Set-Cookie"])

    def test_the_right_password_gives_a_session_cookie_scripts_cannot_read(self):
        response = self.login()

        self.assertEqual(response.status, 200)
        self.assertIn("HttpOnly", response.headers["Set-Cookie"])
        self.assertIn("SameSite=Strict", response.headers["Set-Cookie"])
        self.assertEqual(self.request("GET", "/api/state")[0].status, 200)

    def test_through_the_tunnel_the_cookie_is_only_ever_sent_over_https(self):
        direct, _ = self.request("POST", "/api/login", {"password": PASSWORD})
        tunnelled, _ = self.request("POST", "/api/login", {"password": PASSWORD}, headers={"X-Forwarded-Proto": "https"})

        self.assertNotIn("Secure", direct.headers["Set-Cookie"])
        self.assertIn("; Secure", tunnelled.headers["Set-Cookie"])

    def test_a_stranger_guessing_through_the_tunnel_does_not_lock_the_owner_out(self):
        stranger = {"CF-Connecting-IP": "198.51.100.9"}
        for _ in range(auth.MAX_FAILURES):
            self.request("POST", "/api/login", {"password": "wrong"}, headers=stranger)

        blocked, _ = self.request("POST", "/api/login", {"password": PASSWORD}, headers=stranger)
        owner, _ = self.request("POST", "/api/login", {"password": PASSWORD}, headers={"CF-Connecting-IP": "203.0.113.50"})

        self.assertEqual((blocked.status, owner.status), (429, 200))

    def test_guessing_is_cut_off_even_for_the_right_password(self):
        for _ in range(auth.MAX_FAILURES):
            self.request("POST", "/api/login", {"password": "wrong"})

        response, body = self.request("POST", "/api/login", {"password": PASSWORD})

        self.assertEqual((response.status, body["error"]), (429, "locked"))

    def test_signing_out_ends_the_session(self):
        self.login()
        self.request("POST", "/api/logout")

        self.assertEqual(self.request("GET", "/api/state")[0].status, 401)

    def test_a_change_without_the_header_a_browser_cannot_forge_is_refused(self):
        self.login()

        response, body = self.request("POST", "/api/devices", {"name": "phone"}, csrf=False)

        self.assertEqual((response.status, body["error"]), (403, "csrf"))
        self.assertEqual(self.manager.devices(), [])


class DevicesApiTest(WebTestCase):
    def setUp(self):
        super().setUp()
        self.login()

    def test_adding_a_device_returns_its_settings_and_qr_code(self):
        response, body = self.request("POST", "/api/devices", {"name": "phone"})

        self.assertEqual(response.status, 201)
        self.assertIn("Endpoint = 203.0.113.7:51820", body["config"])
        self.assertTrue(body["qr"].startswith("data:image/svg+xml;base64,"))
        self.assertEqual([device["name"] for device in self.manager.devices()], ["phone"])

    def test_a_refused_name_explains_itself(self):
        response, body = self.request("POST", "/api/devices", {"name": "my phone"})

        self.assertEqual((response.status, body["error"]), (400, "refused"))
        self.assertIn("device name", body["message"])

    def test_state_lists_devices_with_their_status(self):
        self.request("POST", "/api/devices", {"name": "phone"})

        _, body = self.request("GET", "/api/state")

        self.assertEqual(body["devices"][0]["name"], "phone")
        self.assertFalse(body["devices"][0]["online"])
        self.assertEqual(body["server"]["port"], 51820)

    def test_state_never_exposes_a_key_or_the_password_hash(self):
        self.request("POST", "/api/devices", {"name": "phone"})

        text = json.dumps(self.request("GET", "/api/state")[1])

        for secret in ("private", "psk-", "salt", "hash"):
            self.assertNotIn(secret, text)

    def test_disable_enable_and_remove(self):
        self.request("POST", "/api/devices", {"name": "phone"})

        self.request("POST", "/api/devices/phone/disable")
        self.assertFalse(self.manager.devices()[0]["enabled"])
        self.request("POST", "/api/devices/phone/enable")
        self.assertTrue(self.manager.devices()[0]["enabled"])
        self.request("DELETE", "/api/devices/phone")
        self.assertEqual(self.manager.devices(), [])

    def test_the_settings_file_downloads_under_the_device_name(self):
        self.request("POST", "/api/devices", {"name": "phone"})

        response, body = self.request("GET", "/api/devices/phone/config")

        self.assertEqual(response.headers["Content-Disposition"], 'attachment; filename="phone.conf"')
        self.assertTrue(body.startswith("[Interface]"))

    def test_the_backup_download_is_a_restore_file(self):
        response, body = self.request("GET", "/api/backup/download")

        self.assertEqual(response.status, 200)
        self.assertIn("restore_data() {", body)

    def test_malformed_requests_are_answered_not_dropped(self):
        for body in ([], "text", {"name": 5}, {}):
            response, _ = self.request("POST", "/api/devices", body)
            self.assertEqual(response.status, 400, body)


class S3ApiTest(WebTestCase):
    BUCKET = {"endpoint": "https://account.r2.cloudflarestorage.com", "bucket": "b", "access_key": "AKID", "secret_key": "SECRET"}

    def setUp(self):
        super().setUp()
        self.login()

    def test_a_bucket_is_saved_only_after_a_test_upload_works(self):
        self.manager.upload = lambda settings, host, text: "byteguard/first.sh"

        response, body = self.request("POST", "/api/backup/s3", self.BUCKET)

        self.assertEqual((response.status, body["key"]), (200, "byteguard/first.sh"))
        self.assertTrue(self.request("GET", "/api/state")[1]["backup"]["s3"])

    def test_a_failed_test_upload_saves_nothing(self):
        def upload(settings, host, text):
            raise ByteGuardError("The storage answered with HTTP 403 (InvalidAccessKeyId).")

        self.manager.upload = upload

        response, body = self.request("POST", "/api/backup/s3", self.BUCKET)

        self.assertEqual(response.status, 400)
        self.assertIn("InvalidAccessKeyId", body["message"])
        self.assertIsNone(self.manager.s3_settings())

    def test_a_plain_http_endpoint_is_refused(self):
        response, _ = self.request("POST", "/api/backup/s3", {**self.BUCKET, "endpoint": "http://storage.example"})

        self.assertEqual(response.status, 400)
        self.assertIsNone(self.manager.s3_settings())

    def test_the_secret_never_comes_back_in_the_state(self):
        self.manager.upload = lambda settings, host, text: "k"
        self.request("POST", "/api/backup/s3", self.BUCKET)

        self.assertNotIn("SECRET", json.dumps(self.request("GET", "/api/state")[1]))


class StaticTest(WebTestCase):
    def test_the_page_and_its_files_are_served_without_signing_in(self):
        for path, marker in (("/", "<title>ByteGuard</title>"), ("/app.js", "use strict"), ("/i18n/ar.json", "الأجهزة")):
            response, body = self.request("GET", path)
            self.assertEqual(response.status, 200, path)
            self.assertIn(marker, body if isinstance(body, str) else json.dumps(body, ensure_ascii=False))

    def test_every_response_forbids_framing_and_outside_scripts(self):
        response, _ = self.request("GET", "/")

        self.assertIn("default-src 'self'", response.headers["Content-Security-Policy"])
        self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")

    def test_paths_outside_the_static_folder_are_not_served(self):
        for path in ("/../server.py", "/..%2fserver.py", "/../../manager.py", "/i18n/../../auth.py", "/missing.css"):
            self.assertEqual(self.request("GET", path)[0].status, 404, path)


class UiSettingsTest(unittest.TestCase):
    def manager(self, **outputs) -> Manager:
        manager = Manager(temp_paths(self), FakeRun(outputs=outputs))
        manager.set_up(iface="eth0", endpoint="203.0.113.7", port=51820)
        return manager

    def test_turning_it_on_starts_a_confined_service_and_gives_the_vpn_address(self):
        manager = self.manager()

        address = manager.enable_ui(PASSWORD)

        unit = manager.paths.ui_unit.read_text()
        self.assertEqual(address, "http://10.66.66.1:51821")
        self.assertIn("CapabilityBoundingSet=CAP_NET_ADMIN", unit)
        self.assertIn("ProtectSystem=strict", unit)
        self.assertIn("systemctl enable byteguard-ui", manager.run.ran("systemctl"))

    def test_with_ufw_only_traffic_from_the_vpn_may_reach_it(self):
        manager = self.manager(**UFW_ACTIVE)

        manager.enable_ui(PASSWORD)

        self.assertIn("ufw allow in on wg0 to any port 51821 proto tcp comment ByteGuard", manager.run.ran("ufw"))

    def test_without_ufw_the_rule_is_limited_to_the_vpn_interface_and_survives_a_restart(self):
        manager = self.manager()
        manager.run.failing.add("iptables -w -C INPUT -i wg0 -p tcp --dport 51821 -j ACCEPT")

        manager.enable_ui(PASSWORD)

        self.assertIn("iptables -w -I INPUT -i wg0 -p tcp --dport 51821 -j ACCEPT", manager.run.ran("iptables"))
        self.assertIn("PostUp = iptables -w -I INPUT -i %i -p tcp --dport 51821 -j ACCEPT", manager.paths.wg_conf.read_text())

    def test_a_short_password_is_refused(self):
        manager = self.manager()

        with self.assertRaises(ByteGuardError):
            manager.enable_ui("short")

        self.assertIsNone(manager.ui())

    def test_turning_it_off_removes_the_service_and_the_rule(self):
        manager = self.manager(**UFW_ACTIVE)
        manager.enable_ui(PASSWORD)

        manager.disable_ui()

        self.assertIsNone(manager.ui())
        self.assertFalse(manager.paths.ui_unit.exists())
        self.assertIn("ufw delete allow in on wg0 to any port 51821 proto tcp", manager.run.ran("ufw"))

    def test_uninstalling_takes_the_web_interface_with_it(self):
        manager = self.manager()
        manager.enable_ui(PASSWORD)

        manager.uninstall()

        self.assertFalse(manager.paths.ui_unit.exists())
        self.assertIn("systemctl disable --now byteguard-ui", manager.run.ran("systemctl"))

    def test_a_restore_brings_the_web_interface_back_with_its_password(self):
        manager = self.manager()
        manager.enable_ui(PASSWORD)
        saved = manager.state_for_backup()
        fresh = Manager(temp_paths(self), FakeRun())

        fresh.restore(saved, iface="eth0")

        self.assertTrue(fresh.paths.ui_unit.exists())
        self.assertTrue(auth.verify_password(PASSWORD, fresh.ui()["password"]))


if __name__ == "__main__":
    unittest.main()
