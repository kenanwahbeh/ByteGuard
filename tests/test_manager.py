import unittest

from byteguard import firewall, state
from byteguard.errors import ByteGuardError
from byteguard.manager import Manager
from fakes import FakeRun, temp_paths

UFW_ACTIVE = {"ufw status": "Status: active\n"}


class ManagerTestCase(unittest.TestCase):
    def manager(self, **run_options) -> Manager:
        return Manager(temp_paths(self), FakeRun(**run_options))

    def set_up(self, **run_options) -> Manager:
        manager = self.manager(**run_options)
        manager.set_up(iface="eth0", endpoint="203.0.113.7", port=51820)
        return manager


class SetUpTest(ManagerTestCase):
    def test_it_records_the_answers_and_the_agreed_defaults(self):
        server = self.set_up().server()

        self.assertEqual((server["iface"], server["endpoint"], server["port"]), ("eth0", "203.0.113.7", 51820))
        self.assertEqual((server["mtu"], server["keepalive"]), (1420, 25))
        self.assertEqual(server["public_key"], f"public-of-{server['private_key']}")

    def test_it_writes_the_config_and_starts_the_interface_at_boot_and_now(self):
        manager = self.set_up()

        self.assertIn("ListenPort = 51820", manager.paths.wg_conf.read_text())
        self.assertEqual(manager.run.ran("systemctl"), ["systemctl enable --now wg-quick@wg0"])

    def test_with_ufw_active_it_opens_the_port_through_ufw(self):
        manager = self.set_up(outputs=UFW_ACTIVE)

        self.assertIn("ufw allow 51820/udp comment ByteGuard", manager.run.ran("ufw"))
        self.assertNotIn("INPUT", manager.paths.wg_conf.read_text())

    def test_without_ufw_the_rules_live_in_the_interface_hooks(self):
        manager = self.set_up()

        self.assertEqual(manager.run.ran("ufw"), ["ufw status"])
        self.assertIn("PostUp = iptables -w -I FORWARD -i %i -j ACCEPT", manager.paths.wg_conf.read_text())

    def test_a_chosen_network_gives_the_server_its_first_address_and_devices_the_next(self):
        manager = self.manager()
        manager.set_up(iface="eth0", endpoint="203.0.113.7", port=51820, subnet="10.11.12.0/24")

        self.assertEqual(manager.server()["address"], "10.11.12.1")
        self.assertEqual(manager.add_device("phone")["address"], "10.11.12.2")
        self.assertIn("-s 10.11.12.0/24 -o eth0 -j MASQUERADE", manager.paths.wg_conf.read_text())

    def test_a_network_that_is_public_malformed_or_too_small_is_refused(self):
        for subnet in ("8.8.8.0/24", "ten", "10.11.12.0/31"):
            manager = self.manager()
            with self.subTest(subnet=subnet), self.assertRaises(ByteGuardError):
                manager.set_up(iface="eth0", endpoint="203.0.113.7", port=51820, subnet=subnet)
            self.assertEqual(manager.run.calls, [])

    def test_it_refuses_to_run_twice(self):
        manager = self.set_up()

        with self.assertRaises(ByteGuardError):
            manager.set_up(iface="eth0", endpoint="203.0.113.7", port=51820)

    def test_it_refuses_to_overwrite_a_wireguard_setup_it_did_not_create(self):
        manager = self.manager()
        manager.paths.wireguard.mkdir(parents=True)
        manager.paths.wg_conf.write_text("[Interface]\n")

        with self.assertRaises(ByteGuardError):
            manager.set_up(iface="eth0", endpoint="203.0.113.7", port=51820)

        self.assertEqual(manager.paths.wg_conf.read_text(), "[Interface]\n")
        self.assertEqual(manager.run.calls, [])

    def test_a_failed_start_leaves_the_server_as_it_was(self):
        manager = self.manager(outputs=UFW_ACTIVE, failing={"systemctl enable --now wg-quick@wg0"})

        with self.assertRaises(ByteGuardError):
            manager.set_up(iface="eth0", endpoint="203.0.113.7", port=51820)

        self.assertFalse(manager.is_set_up())
        self.assertFalse(manager.paths.wg_conf.exists())
        self.assertFalse(manager.paths.sysctl.exists())
        self.assertIn("ufw delete allow 51820/udp", manager.run.ran("ufw"))


class DeviceTest(ManagerTestCase):
    def test_devices_get_consecutive_addresses_and_their_own_keys(self):
        manager = self.set_up()

        phone = manager.add_device("phone")
        laptop = manager.add_device("laptop")

        self.assertEqual((phone["address"], laptop["address"]), ("10.66.66.2", "10.66.66.3"))
        self.assertNotEqual(phone["private_key"], laptop["private_key"])
        self.assertNotEqual(phone["preshared_key"], laptop["preshared_key"])

    def test_a_change_is_applied_to_the_running_interface_without_restarting_it(self):
        manager = self.set_up()

        manager.add_device("phone")

        self.assertEqual(manager.run.ran("wg-quick"), [f"wg-quick strip {manager.paths.wg_conf}"])
        (synced,) = manager.run.ran("wg syncconf wg0 ")
        # AppArmor confines `wg` to /etc/wireguard, so the file has to be there.
        self.assertTrue(synced.startswith(f"wg syncconf wg0 {manager.paths.wireguard}/"), synced)
        self.assertEqual(manager.run.ran("systemctl"), ["systemctl enable --now wg-quick@wg0"])

    def test_with_the_interface_down_the_change_waits_in_the_config_file(self):
        manager = self.set_up(interface_up=False)

        manager.add_device("phone")

        self.assertEqual(manager.run.ran("wg syncconf"), [])
        self.assertIn("# phone", manager.paths.wg_conf.read_text())

    def test_a_second_device_with_the_same_name_is_refused(self):
        manager = self.set_up()
        manager.add_device("phone")

        with self.assertRaises(ByteGuardError):
            manager.add_device("phone")

        self.assertEqual(len(manager.devices()), 1)

    def test_a_bad_name_is_refused_before_anything_changes(self):
        manager = self.set_up()
        before = len(manager.run.calls)

        with self.assertRaises(ByteGuardError):
            manager.add_device("my phone")

        self.assertEqual(len(manager.run.calls), before)

    def test_a_disabled_device_is_kept_but_cannot_connect(self):
        manager = self.set_up()
        manager.add_device("phone")

        manager.set_enabled("phone", False)

        self.assertFalse(manager.devices()[0]["enabled"])
        self.assertNotIn("# phone", manager.paths.wg_conf.read_text())

        manager.set_enabled("phone", True)

        self.assertIn("# phone", manager.paths.wg_conf.read_text())

    def test_a_removed_device_is_gone_and_its_address_is_free_again(self):
        manager = self.set_up()
        manager.add_device("phone")

        manager.remove_device("phone")

        self.assertEqual(manager.devices(), [])
        self.assertEqual(manager.add_device("tablet")["address"], "10.66.66.2")

    def test_an_unknown_device_is_an_error(self):
        manager = self.set_up()

        for action in (manager.remove_device, manager.client_config, lambda n: manager.set_enabled(n, False)):
            with self.assertRaises(ByteGuardError):
                action("ghost")

    def test_the_qr_code_encodes_the_device_config(self):
        manager = self.set_up(outputs={"qrencode -t ansiutf8": "QR\n"})
        manager.add_device("phone")

        self.assertEqual(manager.qr_code("phone"), "QR\n")

    def test_commands_before_setup_say_how_to_set_up(self):
        with self.assertRaisesRegex(ByteGuardError, "byteguard setup"):
            self.manager().devices()


class StatusTest(ManagerTestCase):
    def test_live_figures_are_matched_to_devices_by_public_key(self):
        manager = self.set_up()
        phone = manager.add_device("phone")
        manager.add_device("laptop")
        manager.run.outputs["wg show wg0 dump"] = (
            "server-private\tserver-public\t51820\toff\n"
            f"{phone['public_key']}\tpsk\t198.51.100.4:40000\t10.66.66.2/32\t0\t10\t20\t25\n"
        )

        phone_status, laptop_status = manager.status()

        self.assertEqual((phone_status["received"], phone_status["sent"]), (10, 20))
        self.assertEqual((laptop_status["received"], laptop_status["online"]), (0, False))


class UninstallTest(ManagerTestCase):
    def test_it_removes_the_interface_the_rules_the_keys_and_the_program(self):
        manager = self.set_up(outputs=UFW_ACTIVE)
        manager.paths.program.mkdir(parents=True)
        manager.paths.launcher.parent.mkdir(parents=True)
        manager.paths.launcher.write_text("")

        manager.uninstall()

        self.assertIn("systemctl disable --now wg-quick@wg0", manager.run.ran("systemctl"))
        self.assertEqual(
            manager.run.ran("ufw")[-2:],
            ["ufw delete allow 51820/udp", "ufw route delete allow in on wg0 out on eth0"],
        )
        for path in (manager.paths.etc, manager.paths.wg_conf, manager.paths.sysctl,
                     manager.paths.program, manager.paths.launcher):
            self.assertFalse(path.exists(), path)

    def test_it_never_turns_forwarding_off(self):
        manager = self.set_up()

        manager.uninstall()

        self.assertEqual(manager.run.ran("sysctl"), ["sysctl -q -w net.ipv4.ip_forward=1"])

    def test_on_a_server_that_was_never_set_up_it_leaves_other_wireguard_configs_alone(self):
        manager = self.manager()
        manager.paths.wireguard.mkdir(parents=True)
        manager.paths.wg_conf.write_text("[Interface]\n")

        manager.uninstall()

        self.assertTrue(manager.paths.wg_conf.exists())
        self.assertEqual(manager.run.calls, [])


class FirewallModeTest(ManagerTestCase):
    def test_the_mode_found_at_setup_is_the_one_used_to_undo_it(self):
        manager = self.set_up(outputs=UFW_ACTIVE)

        self.assertEqual(state.load(manager.paths.state)["firewall"]["mode"], firewall.UFW)


if __name__ == "__main__":
    unittest.main()
