import json
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

from byteguard import backup
from byteguard.errors import ByteGuardError
from byteguard.manager import Manager
from fakes import FakeRun, temp_paths


class Sent:
    """Stands in for Telegram: records what was sent, or refuses."""

    def __init__(self, error=None):
        self.calls = []
        self.error = error

    def __call__(self, token, chat_id, filename, content, caption):
        if self.error:
            raise ByteGuardError(self.error)
        self.calls.append((token, chat_id, filename, content, caption))


class BackupTestCase(unittest.TestCase):
    def setUp(self):
        self.sent = Sent()
        self.manager = Manager(temp_paths(self), FakeRun(), self.sent)
        self.manager.set_up(iface="eth0", endpoint="203.0.113.7", port=51820)

    def local_backup(self) -> Path:
        return self.manager.paths.backups / backup.file_name()

    def data_inside(self, script: str) -> dict:
        """Run the backup's own restore_data function and return what it writes."""
        work = Path(tempfile.mkdtemp())
        self.addCleanup(__import__("shutil").rmtree, work, ignore_errors=True)
        body = script.rstrip("\n").rpartition("\n")[0]
        (work / "extract.sh").write_text(body + '\nrestore_data "$1"\n')
        subprocess.run(["bash", str(work / "extract.sh"), str(work / "data.json")], check=True)
        return backup.read_payload(work / "data.json")


class AutomaticBackupTest(BackupTestCase):
    def test_every_change_rewrites_the_backup_with_the_new_state(self):
        self.manager.add_device("phone")
        self.assertEqual(len(self.data_inside(self.local_backup().read_text())["state"]["devices"]), 1)

        self.manager.add_device("laptop")
        self.manager.set_enabled("phone", False)
        devices = self.data_inside(self.local_backup().read_text())["state"]["devices"]

        self.assertEqual([(d["name"], d["enabled"]) for d in devices], [("phone", False), ("laptop", True)])

    def test_the_backup_is_a_runnable_installer_that_only_root_can_read(self):
        path = self.local_backup()

        self.assertEqual(subprocess.run(["bash", "-n", str(path)]).returncode, 0)
        self.assertIn("extract_payload() {", path.read_text())
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_with_telegram_set_every_change_is_sent_there_too(self):
        self.manager.set_telegram("bot-token", 42)
        self.manager.add_device("phone")

        token, chat_id, filename, content, caption = self.sent.calls[-1]
        self.assertEqual((token, chat_id, filename), ("bot-token", 42, backup.file_name()))
        self.assertEqual(content, self.local_backup().read_text())
        self.assertIn("1 device.", caption)

    def test_the_backup_carries_the_destination_settings_so_a_restore_keeps_sending(self):
        self.manager.set_telegram("bot-token", 42)

        saved = self.data_inside(self.local_backup().read_text())["state"]

        self.assertEqual(saved["backup"]["telegram"], {"token": "bot-token", "chat_id": 42})

    def test_a_failed_send_is_reported_but_the_change_still_happens(self):
        self.manager.set_telegram("bot-token", 42)
        self.sent.error = "Telegram could not be reached."

        self.manager.add_device("phone")

        self.assertEqual([d["name"] for d in self.manager.devices()], ["phone"])
        self.assertEqual(self.manager.last_backup["telegram"], {"ok": False, "error": "Telegram could not be reached."})
        self.assertTrue(self.manager.last_backup["local"]["ok"])
        status = json.loads(self.manager.paths.backup_status.read_text())
        self.assertFalse(status["telegram"]["ok"])

    def test_turning_telegram_off_stops_the_sending(self):
        self.manager.set_telegram("bot-token", 42)
        self.manager.set_telegram(None)
        before = len(self.sent.calls)

        self.manager.add_device("phone")

        self.assertEqual(len(self.sent.calls), before)
        self.assertIsNone(self.manager.telegram_chat())


class RestoreTest(BackupTestCase):
    def restored(self, **run_options) -> Manager:
        self.manager.add_device("phone")
        saved = self.data_inside(self.local_backup().read_text())["state"]
        fresh = Manager(temp_paths(self), FakeRun(**run_options), self.sent)
        fresh.restore(saved, iface="ens3")
        return fresh

    def test_the_server_and_its_devices_come_back_with_the_same_keys(self):
        fresh = self.restored()

        self.assertEqual(fresh.server()["private_key"], self.manager.server()["private_key"])
        self.assertEqual(fresh.client_config("phone"), self.manager.client_config("phone"))
        self.assertIn("# phone", fresh.paths.wg_conf.read_text())
        self.assertEqual(fresh.run.ran("systemctl"), ["systemctl enable --now wg-quick@wg0"])

    def test_it_uses_the_new_servers_network_card_and_firewall(self):
        fresh = self.restored(outputs={"ufw status": "Status: active\n"})

        self.assertEqual(fresh.server()["iface"], "ens3")
        self.assertIn("ufw route allow in on wg0 out on ens3 comment ByteGuard", fresh.run.ran("ufw"))

    def test_it_does_not_generate_any_new_key(self):
        self.assertEqual(self.restored().run.ran("wg gen"), [])

    def test_it_refuses_a_server_that_is_already_set_up(self):
        saved = self.data_inside(self.local_backup().read_text())["state"]

        with self.assertRaises(ByteGuardError):
            self.manager.restore(saved, iface="eth0")


class PayloadTest(unittest.TestCase):
    def test_a_file_that_is_not_backup_data_is_refused(self):
        work = Path(tempfile.mkdtemp())
        self.addCleanup(__import__("shutil").rmtree, work, ignore_errors=True)
        for name, text in (("empty", ""), ("other", '{"state": {}}'), ("schema", '{"state": {"schema": 99, "server": {"private_key": "k"}}}')):
            (work / name).write_text(text)
            with self.subTest(name=name), self.assertRaises(ByteGuardError):
                backup.read_payload(work / name)


if __name__ == "__main__":
    unittest.main()
