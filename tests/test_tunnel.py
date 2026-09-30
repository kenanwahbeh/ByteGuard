import json
import unittest

from byteguard import tunnel
from byteguard.errors import ByteGuardError
from byteguard.manager import Manager
from fakes import FakeRun, temp_paths

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
        self.assertTrue(tunnel.other_tunnel_running(FakeRun()))
        self.assertFalse(tunnel.other_tunnel_running(FakeRun(failing={"systemctl is-active --quiet cloudflared"})))

    def test_an_unknown_architecture_is_not_downloaded_blindly(self):
        run = FakeRun(outputs={"dpkg --print-architecture": "riscv64\n"})

        with self.assertRaises(ByteGuardError):
            tunnel.install(run, download=lambda url, path: self.fail("downloaded"))


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

    def test_a_restore_brings_the_tunnel_back_without_signing_in_again(self):
        saved = self.with_tunnel().state_for_backup()
        fresh = Manager(temp_paths(self), FakeRun(outputs={"sh -c command -v cloudflared": "/usr/bin/cloudflared\n"}))

        fresh.restore(saved, iface="eth0")

        self.assertTrue(fresh.paths.tunnel_unit.exists())
        self.assertEqual(fresh.run.ran("cloudflared tunnel login"), [])
        self.assertIn("systemctl restart byteguard-tunnel", fresh.run.ran("systemctl"))


if __name__ == "__main__":
    unittest.main()
