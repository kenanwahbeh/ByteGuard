import contextlib
import io
import json
import unittest
from unittest import mock

from byteguard import __version__, state
from byteguard.cli import main
from byteguard.manager import Manager
from fakes import FakeRun, temp_paths


class CliTestCase(unittest.TestCase):
    def setUp(self):
        self.manager = Manager(temp_paths(self), FakeRun(outputs={"qrencode -t ansiutf8": "QR\n"}))

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(list(argv), self.manager)
        return code, out.getvalue(), err.getvalue()

    def set_up(self):
        self.manager.set_up(iface="eth0", endpoint="203.0.113.7", port=51820)


class BasicsTest(CliTestCase):
    def test_version_flag_prints_the_version_and_exits_cleanly(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit) as raised:
            main(["--version"])

        self.assertEqual(raised.exception.code, 0)
        self.assertEqual(out.getvalue().strip(), f"byteguard {__version__}")

    def test_no_arguments_shows_the_help(self):
        code, out, _ = self.run_cli()

        self.assertEqual(code, 0)
        self.assertIn("usage: byteguard", out)

    def test_a_failure_is_one_line_on_stderr_and_a_nonzero_exit(self):
        code, out, err = self.run_cli("list")

        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertTrue(err.startswith("error: This server is not set up yet."))
        self.assertEqual(err.count("\n"), 1)


class DeviceCommandsTest(CliTestCase):
    def test_add_prints_the_config_and_the_qr_code(self):
        self.set_up()

        code, out, _ = self.run_cli("add", "phone")

        self.assertEqual(code, 0)
        self.assertIn("Endpoint = 203.0.113.7:51820", out)
        self.assertIn("QR\n", out)

    def test_show_can_print_the_config_alone(self):
        self.set_up()
        self.manager.add_device("phone")

        _, out, _ = self.run_cli("show", "phone", "--no-qr")

        self.assertTrue(out.startswith("[Interface]\n"))
        self.assertNotIn("QR", out)

    def test_list_marks_disabled_devices(self):
        self.set_up()
        self.manager.add_device("phone")
        self.manager.add_device("laptop")
        self.run_cli("disable", "laptop")

        _, out, _ = self.run_cli("list")

        phone, laptop = out.splitlines()
        self.assertNotIn("disabled", phone)
        self.assertIn("(disabled)", laptop)

    def test_status_shows_a_device_that_never_connected(self):
        self.set_up()
        self.manager.add_device("phone")

        _, out, _ = self.run_cli("status")

        self.assertIn("never connected", out)
        self.assertIn("received 0 B, sent 0 B", out)

    def test_remove_deletes_the_device(self):
        self.set_up()
        self.manager.add_device("phone")

        self.run_cli("remove", "phone")

        self.assertEqual(self.manager.devices(), [])


class SetupCommandTest(CliTestCase):
    def test_non_interactive_setup_creates_the_server_and_the_first_device(self):
        self.manager.run.outputs.update(
            {
                "ip -4 route show default": "default via 203.0.113.1 dev ens3\n",
                "ip -4 -o addr show scope global": "2: ens3    inet 203.0.113.7/26 scope global ens3\\\n",
            }
        )

        code, out, err = self.run_cli(
            "setup", "--non-interactive", "--endpoint", "vpn.example.com", "--port", "40000", "--first-device", "tv"
        )

        self.assertEqual((code, err), (0, ""))
        self.assertEqual([device["name"] for device in self.manager.devices()], ["tv"])
        self.assertIn("Endpoint = vpn.example.com:40000", out)

    def test_setup_on_a_server_that_is_already_set_up_is_refused(self):
        self.set_up()

        code, _, err = self.run_cli("setup", "--non-interactive")

        self.assertEqual(code, 1)
        self.assertIn("already set up", err)


class BackupCommandTest(CliTestCase):
    NETWORK = {
        "ip -4 route show default": "default via 203.0.113.1 dev ens3\n",
        "ip -4 -o addr show scope global": "2: ens3    inet 203.0.113.7/26 scope global ens3\\\n",
    }

    def payload_file(self):
        """Backup data as a backup script would hand it to `byteguard restore`."""
        self.set_up()
        self.manager.add_device("phone")
        path = self.manager.paths.etc.parent / "payload.json"
        payload = {"made_at": "2026-09-30T12:00:00+00:00", "host": "old", "state": state.load(self.manager.paths.state)}
        path.write_text(json.dumps(payload))
        return path

    def fresh_server(self, **outputs):
        self.manager = Manager(temp_paths(self), FakeRun(outputs={**self.NETWORK, **outputs}))

    def test_backup_says_where_the_file_is_and_that_it_is_not_encrypted(self):
        self.set_up()

        code, out, _ = self.run_cli("backup")

        self.assertEqual(code, 0)
        self.assertIn(str(self.manager.paths.backups), out)
        self.assertIn("not encrypted", out)

    def test_restore_brings_the_devices_back_on_a_fresh_server(self):
        path = self.payload_file()
        self.fresh_server()

        code, out, err = self.run_cli("restore", str(path), "--yes")

        self.assertEqual((code, err), (0, ""))
        self.assertEqual([device["name"] for device in self.manager.devices()], ["phone"])
        self.assertEqual(self.manager.server()["iface"], "ens3")
        self.assertNotIn("warning", out)

    def test_restore_warns_when_the_devices_point_at_another_address(self):
        path = self.payload_file()
        self.fresh_server(**{"ip -4 -o addr show scope global": "2: ens3    inet 198.51.100.9/26 scope global ens3\\\n"})

        with mock.patch("byteguard.netdetect.public_address", return_value="198.51.100.9"):
            _, out, _ = self.run_cli("restore", str(path), "--yes")

        self.assertIn("warning: the devices connect to 203.0.113.7", out)

    def test_restore_with_a_new_endpoint_rewrites_the_device_settings(self):
        path = self.payload_file()
        self.fresh_server()

        self.run_cli("restore", str(path), "--yes", "--endpoint", "vpn.example.com")

        self.assertIn("Endpoint = vpn.example.com:51820", self.manager.client_config("phone"))


class UninstallCommandTest(CliTestCase):
    def test_with_yes_it_removes_everything_without_asking(self):
        self.set_up()

        code, out, _ = self.run_cli("uninstall", "--yes")

        self.assertEqual(code, 0)
        self.assertFalse(self.manager.is_set_up())
        self.assertIn("was removed", out)


if __name__ == "__main__":
    unittest.main()
