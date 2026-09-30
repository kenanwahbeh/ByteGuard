import unittest

from byteguard import firewall
from fakes import FakeRun, temp_paths


class DetectTest(unittest.TestCase):
    def test_an_active_ufw_is_used(self):
        run = FakeRun(outputs={"ufw status": "Status: active\n"})

        self.assertEqual(firewall.detect(run), firewall.UFW)

    def test_an_inactive_ufw_is_ignored(self):
        run = FakeRun(outputs={"ufw status": "Status: inactive\n"})

        self.assertEqual(firewall.detect(run), firewall.IPTABLES)

    def test_a_server_without_ufw_uses_iptables(self):
        self.assertEqual(firewall.detect(FakeRun(missing={"ufw"})), firewall.IPTABLES)


class HooksTest(unittest.TestCase):
    def test_with_ufw_only_the_address_translation_is_a_hook(self):
        up, down = firewall.hooks(firewall.UFW, "eth0", 51820, "10.66.66.0/24")

        self.assertEqual(up, ["iptables -w -t nat -A POSTROUTING -s 10.66.66.0/24 -o eth0 -j MASQUERADE"])
        self.assertEqual(down, ["iptables -w -t nat -D POSTROUTING -s 10.66.66.0/24 -o eth0 -j MASQUERADE"])

    def test_without_ufw_the_port_and_forwarding_go_ahead_of_existing_rules(self):
        up, _ = firewall.hooks(firewall.IPTABLES, "eth0", 51820, "10.66.66.0/24")

        self.assertIn("iptables -w -I INPUT -p udp --dport 51820 -j ACCEPT", up)
        self.assertIn("iptables -w -I FORWARD -i %i -j ACCEPT", up)

    def test_every_rule_added_is_removed_by_the_same_text(self):
        for mode in (firewall.UFW, firewall.IPTABLES):
            up, down = firewall.hooks(mode, "eth0", 51820, "10.66.66.0/24")

            removed = [command.replace(" -D ", " -X ") for command in down]
            added = [command.replace(" -A ", " -X ").replace(" -I ", " -X ") for command in up]
            self.assertEqual(added, removed)

    def test_no_hook_flushes_a_chain_or_changes_a_policy(self):
        for mode in (firewall.UFW, firewall.IPTABLES):
            for command in sum(firewall.hooks(mode, "eth0", 51820, "10.66.66.0/24"), []):
                self.assertNotRegex(command, r" -[FPX] ")


class UfwRulesTest(unittest.TestCase):
    def test_opening_allows_the_port_and_the_forwarding(self):
        run = FakeRun()

        firewall.open_ports(run, firewall.UFW, "eth0", 51820)

        self.assertEqual(
            run.ran("ufw"),
            [
                "ufw allow 51820/udp comment ByteGuard",
                "ufw route allow in on wg0 out on eth0 comment ByteGuard",
            ],
        )

    def test_closing_deletes_exactly_those_rules(self):
        run = FakeRun()

        firewall.close_ports(run, firewall.UFW, "eth0", 51820)

        self.assertEqual(
            run.ran("ufw"),
            ["ufw delete allow 51820/udp", "ufw route delete allow in on wg0 out on eth0"],
        )

    def test_without_ufw_no_ufw_command_is_run(self):
        run = FakeRun()

        firewall.open_ports(run, firewall.IPTABLES, "eth0", 51820)
        firewall.close_ports(run, firewall.IPTABLES, "eth0", 51820)

        self.assertEqual(run.calls, [])


class ForwardingTest(unittest.TestCase):
    def test_forwarding_is_turned_on_now_and_for_later_boots(self):
        run = FakeRun()
        sysctl = temp_paths(self).sysctl

        firewall.enable_forwarding(sysctl, run)

        self.assertIn("net.ipv4.ip_forward = 1", sysctl.read_text())
        self.assertEqual(run.ran("sysctl"), ["sysctl -q -w net.ipv4.ip_forward=1"])


if __name__ == "__main__":
    unittest.main()
