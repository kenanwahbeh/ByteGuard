import base64
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from byteguard import tunnel
from byteguard.errors import ByteGuardError
from byteguard.manager import Manager
from fakes import FakeRun, temp_paths

# Cloudflare's package signing key, as served at tunnel.APT_KEY_URL.
CLOUDFLARE_KEY_PACKET = base64.b64decode(
    "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"
    "zNbyacypK7vjJOTAR+ty9S7V8cnajnIWAlcTDg4="
)
# A well-formed version 4 public key packet that is some other key.
OTHER_KEY_PACKET = b"\x99\x00\x06\x04\x00\x00\x00\x00\x01"

CLOUDFLARE = ["ada.ns.cloudflare.com", "bob.ns.cloudflare.com"]
CREATED = {"id": "1234-abcd", "name": "byteguard-vps-ab12", "credentials": {"TunnelID": "1234-abcd", "TunnelSecret": "s3cret"}}


class ZoneTest(unittest.TestCase):
    def test_the_domain_is_the_first_name_up_the_tree_with_name_servers(self):
        records = {"example.co.uk": CLOUDFLARE}
        asked = []

        def lookup(name):
            asked.append(name)
            return records.get(name, [])

        self.assertEqual(tunnel.zone_of("vpn.example.co.uk", lookup), ("example.co.uk", CLOUDFLARE))
        self.assertEqual(asked, ["vpn.example.co.uk", "example.co.uk"])

    def test_a_name_with_no_domain_behind_it_is_an_error(self):
        with self.assertRaisesRegex(ByteGuardError, "No domain was found"):
            tunnel.zone_of("vpn.nothing.example", lambda name: [])

    def test_a_failed_lookup_is_reported_as_a_connection_problem(self):
        def lookup(name):
            raise OSError("unreachable")

        with self.assertRaisesRegex(ByteGuardError, "internet connection"):
            tunnel.zone_of("vpn.example.com", lookup)

    def test_only_cloudflare_name_servers_count_as_on_cloudflare(self):
        self.assertTrue(tunnel.on_cloudflare(CLOUDFLARE))
        self.assertFalse(tunnel.on_cloudflare(["ns1.registrar.example", "ada.ns.cloudflare.com"]))
        self.assertFalse(tunnel.on_cloudflare(["evil-ns.cloudflare.com.attacker.example"]))
        self.assertFalse(tunnel.on_cloudflare([]))


class CloudflaredRun(FakeRun):
    """A cloudflared that writes tunnel credentials when asked to create one."""

    def __call__(self, cmd, *, env=None, **options):
        cmd = list(cmd)
        if cmd[:3] == ["cloudflared", "tunnel", "login"]:
            certificate = __import__("pathlib").Path(env["HOME"]) / ".cloudflared"
            certificate.mkdir()
            (certificate / "cert.pem").write_text("whole-domain certificate")
        if cmd[:3] == ["cloudflared", "tunnel", "create"]:
            __import__("pathlib").Path(cmd[4]).write_text(json.dumps(CREATED["credentials"]))
        return super().__call__(cmd, env=env, **options)


class CreateTest(unittest.TestCase):
    def setUp(self):
        self.home = temp_paths(self).etc / "cloudflared-setup"

    def test_it_signs_in_creates_and_routes_then_keeps_only_the_tunnel_credentials(self):
        run = CloudflaredRun()

        created = tunnel.create(run, self.home, "vpn.example.com")

        self.assertEqual(created["id"], "1234-abcd")
        self.assertEqual(created["credentials"], CREATED["credentials"])
        self.assertEqual(run.ran("cloudflared tunnel route"), ["cloudflared tunnel route dns 1234-abcd vpn.example.com"])
        self.assertFalse(self.home.exists(), "the sign-in certificate was left on the server")

    def test_a_refused_dns_record_explains_what_to_do_and_still_removes_the_certificate(self):
        run = CloudflaredRun(failing={"cloudflared tunnel route dns 1234-abcd vpn.example.com"})

        with self.assertRaisesRegex(ByteGuardError, "already exists"):
            tunnel.create(run, self.home, "vpn.example.com")

        self.assertFalse(self.home.exists())
        # The unused tunnel is deleted while the sign-in still allows it.
        self.assertEqual(run.ran("cloudflared tunnel delete"), ["cloudflared tunnel delete 1234-abcd"])

    def test_a_cancelled_sign_in_leaves_nothing_behind(self):
        run = CloudflaredRun(failing={"cloudflared tunnel login"})

        with self.assertRaises(ByteGuardError):
            tunnel.create(run, self.home, "vpn.example.com")

        self.assertFalse(self.home.exists())
        self.assertEqual(run.ran("cloudflared tunnel create"), [])


class DetectionTest(unittest.TestCase):
    def test_a_missing_cloudflared_is_not_installed(self):
        self.assertFalse(tunnel.installed(FakeRun(missing={"cloudflared"})))
        self.assertTrue(tunnel.installed(FakeRun()))

    def test_an_active_cloudflared_service_is_someone_elses_tunnel(self):
        self.assertTrue(tunnel.other_tunnel_running(FakeRun(active={"cloudflared"})))
        self.assertFalse(tunnel.other_tunnel_running(FakeRun()))



class InstallTest(unittest.TestCase):
    def setUp(self):
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder)
        self.keyring = folder / "keyrings" / "byteguard-cloudflare.gpg"
        self.sources = folder / "sources.list.d"
        self.sources.mkdir()
        self.run = FakeRun()

    def install(self, key):
        tunnel.install(self.run, fetch=lambda url: key, keyring=self.keyring, sources=self.sources)

    def test_the_key_is_pinned_by_its_fingerprint(self):
        self.assertEqual(tunnel.key_fingerprint(CLOUDFLARE_KEY_PACKET), tunnel.APT_KEY_FINGERPRINT)

    def test_cloudflared_comes_from_the_signed_repository(self):
        self.install(CLOUDFLARE_KEY_PACKET)

        self.assertEqual(self.keyring.read_bytes(), CLOUDFLARE_KEY_PACKET)
        source = (self.sources / tunnel.APT_SOURCE_NAME).read_text()
        self.assertEqual(source, f"deb [signed-by={self.keyring}] https://pkg.cloudflare.com/cloudflared any main\n")
        self.assertEqual(self.run.ran("apt-get install"), ["apt-get install -y -qq cloudflared"])

    def test_any_other_key_installs_nothing(self):
        for key in (b"", b"<html>not a key</html>", OTHER_KEY_PACKET):
            with self.subTest(key=key[:10]), self.assertRaises(ByteGuardError):
                self.install(key)
        self.assertFalse(self.keyring.exists())
        self.assertEqual(list(self.sources.iterdir()), [])
        self.assertEqual(self.run.calls, [])

    def test_a_repository_that_is_already_listed_is_not_added_again(self):
        (self.sources / "cloudflared.list").write_text(f"deb {tunnel.APT_REPOSITORY} any main\n")

        tunnel.install(self.run, fetch=lambda url: self.fail("fetched"), keyring=self.keyring, sources=self.sources)

        self.assertFalse((self.sources / tunnel.APT_SOURCE_NAME).exists())
        self.assertEqual(self.run.ran("apt-get install"), ["apt-get install -y -qq cloudflared"])


class ManagerTunnelTest(unittest.TestCase):
    def manager(self) -> Manager:
        manager = Manager(temp_paths(self), FakeRun(outputs={"sh -c command -v cloudflared": "/usr/bin/cloudflared\n"}))
        manager.set_up(iface="eth0", endpoint="203.0.113.7", port=51820)
        return manager

    def with_tunnel(self) -> Manager:
        manager = self.manager()
        manager.enable_ui("correct horse")
        manager.enable_tunnel("vpn.example.com", CREATED)
        return manager

    def test_it_needs_the_web_interface_to_be_on(self):
        with self.assertRaisesRegex(ByteGuardError, "ui setup"):
            self.manager().enable_tunnel("vpn.example.com", CREATED)

    def test_it_serves_the_web_interface_and_nothing_else(self):
        manager = self.with_tunnel()

        config = (manager.paths.tunnel_dir / "config.yml").read_text()
        self.assertIn("  - hostname: vpn.example.com\n    service: http://10.66.66.1:51821\n", config)
        self.assertTrue(config.endswith("  - service: http_status:404\n"))

    def test_it_runs_as_its_own_service_with_its_own_files(self):
        manager = self.with_tunnel()

        unit = manager.paths.tunnel_unit.read_text()
        self.assertIn(f"ExecStart=/usr/bin/cloudflared tunnel --no-autoupdate --config {manager.paths.tunnel_dir}/config.yml run", unit)
        self.assertIn("systemctl enable byteguard-tunnel", manager.run.ran("systemctl"))
        self.assertEqual([c for c in manager.run.ran("systemctl") if c.endswith(" cloudflared")], [])
        self.assertEqual(manager.run.ran("cloudflared service"), [])

    def test_the_credentials_are_private_and_travel_in_the_backup(self):
        manager = self.with_tunnel()
        credentials = manager.paths.tunnel_dir / "1234-abcd.json"

        self.assertEqual(credentials.stat().st_mode & 0o777, 0o600)
        self.assertEqual(manager.state_for_backup()["tunnel"]["credentials"]["TunnelSecret"], "s3cret")

    def test_turning_it_off_removes_the_service_and_the_files(self):
        manager = self.with_tunnel()

        manager.disable_tunnel()

        self.assertIsNone(manager.tunnel())
        self.assertFalse(manager.paths.tunnel_unit.exists())
        self.assertFalse(manager.paths.tunnel_dir.exists())

    def test_turning_the_web_interface_off_takes_the_tunnel_with_it(self):
        manager = self.with_tunnel()

        manager.disable_ui()

        self.assertIsNone(manager.tunnel())
        self.assertFalse(manager.paths.tunnel_unit.exists())

    def test_a_tunnel_that_will_not_stop_is_kept_and_reported(self):
        manager = self.with_tunnel()
        manager.run.active.add("byteguard-tunnel")

        with self.assertRaisesRegex(ByteGuardError, "still public"):
            manager.disable_tunnel()

        self.assertIsNotNone(manager.tunnel())
        self.assertTrue(manager.paths.tunnel_unit.exists())

    def test_a_tunnel_that_fails_to_start_keeps_its_credentials(self):
        manager = self.manager()
        manager.enable_ui("correct horse")
        manager.run.failing.add("systemctl restart byteguard-tunnel")

        with self.assertRaisesRegex(ByteGuardError, "created and saved"):
            manager.enable_tunnel("vpn.example.com", CREATED)

        self.assertEqual(manager.tunnel()["credentials"]["TunnelSecret"], "s3cret")

    def test_changing_the_web_interface_port_moves_the_tunnel_with_it(self):
        manager = self.with_tunnel()

        manager.enable_ui("correct horse", port=52000)

        config = (manager.paths.tunnel_dir / "config.yml").read_text()
        self.assertIn("service: http://10.66.66.1:52000", config)

    def test_a_tunnel_that_fails_during_a_restore_leaves_the_vpn_restored(self):
        saved = self.with_tunnel().state_for_backup()
        fresh = Manager(temp_paths(self), FakeRun(outputs={"sh -c command -v cloudflared": "/usr/bin/cloudflared\n"},
                                                  failing={"systemctl restart byteguard-tunnel"}))

        fresh.restore(saved, iface="eth0")

        self.assertTrue(fresh.is_set_up())
        self.assertIn("systemctl enable --now wg-quick@wg0", fresh.run.ran("systemctl"))
        self.assertTrue(any("tunnel did not start" in warning for warning in fresh.warnings))

    def test_a_restore_brings_the_tunnel_back_without_signing_in_again(self):
        saved = self.with_tunnel().state_for_backup()
        fresh = Manager(temp_paths(self), FakeRun(outputs={"sh -c command -v cloudflared": "/usr/bin/cloudflared\n"}))

        fresh.restore(saved, iface="eth0")

        self.assertTrue(fresh.paths.tunnel_unit.exists())
        self.assertEqual(fresh.run.ran("cloudflared tunnel login"), [])
        self.assertIn("systemctl restart byteguard-tunnel", fresh.run.ran("systemctl"))


if __name__ == "__main__":
    unittest.main()
