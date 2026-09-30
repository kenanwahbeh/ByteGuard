import unittest

from byteguard import wizard
from byteguard.errors import ByteGuardError
from fakes import FakeRun, scripted_terminal

SYSTEM = {
    "ip -4 route show default": "default via 203.0.113.1 dev ens3 proto dhcp\n",
    "ip -4 -o addr show scope global": (
        "2: ens3    inet 203.0.113.7/26 scope global ens3\\\n"
        "3: docker0    inet 172.17.0.1/16 scope global docker0\\\n"
    ),
}


def gather(term=None, **given):
    options = {
        "run": FakeRun(outputs=SYSTEM),
        "term": term,
        "public_address": lambda: "198.51.100.9",
        "port_is_free": lambda port: port != 53,
    }
    return wizard.gather(**{**options, **given})


class NonInteractiveTest(unittest.TestCase):
    def test_everything_missing_is_detected_or_defaulted(self):
        self.assertEqual(gather(), wizard.Answers("ens3", "198.51.100.9", 51820, "phone"))

    def test_given_values_win_over_detection(self):
        answers = gather(iface="docker0", endpoint="vpn.example.com", port=443, first_device="laptop")

        self.assertEqual(answers, wizard.Answers("docker0", "vpn.example.com", 443, "laptop"))

    def test_without_a_public_address_service_the_cards_own_address_is_used(self):
        self.assertEqual(gather(public_address=lambda: None).endpoint, "203.0.113.7")

    def test_bad_values_are_errors_not_questions(self):
        for given in ({"iface": "eth9"}, {"endpoint": "not an address"}, {"port": 70000},
                      {"port": 53}, {"first_device": "my phone"}):
            with self.subTest(given=given), self.assertRaises(ByteGuardError):
                gather(**given)


class InteractiveTest(unittest.TestCase):
    def test_pressing_enter_throughout_accepts_what_was_detected(self):
        term, written = scripted_terminal("", "", "", "", "")

        answers = gather(term)

        self.assertEqual(answers, wizard.Answers("ens3", "198.51.100.9", 51820, "phone"))
        self.assertIn("Internet-facing network card: ens3 (203.0.113.7)\n", written)

    def test_the_summary_shows_what_will_be_applied_before_asking(self):
        term, written = scripted_terminal("", "", "", "", "")

        gather(term)

        summary = "".join(written)
        self.assertIn("WireGuard port   51820/udp", summary)
        self.assertLess(summary.index("WireGuard port   51820/udp"), summary.index("Apply these settings?"))

    def test_declining_the_detected_card_offers_the_others(self):
        term, _ = scripted_terminal("n", "2", "", "", "", "")

        self.assertEqual(gather(term).iface, "docker0")

    def test_an_unusable_port_is_asked_again(self):
        term, written = scripted_terminal("", "", "abc", "53", "443", "", "")

        self.assertEqual(gather(term).port, 443)
        self.assertIn("UDP port 53 is already in use on this server.\n", written)

    def test_an_invalid_address_is_asked_again(self):
        term, _ = scripted_terminal("", "vpn example", "vpn.example.com", "", "", "")

        self.assertEqual(gather(term).endpoint, "vpn.example.com")

    def test_values_given_on_the_command_line_are_not_asked_again(self):
        term, written = scripted_terminal("")

        answers = gather(term, iface="ens3", endpoint="vpn.example.com", port=443, first_device="tv")

        self.assertEqual(answers, wizard.Answers("ens3", "vpn.example.com", 443, "tv"))
        self.assertEqual(sum(1 for text in written if text.endswith(": ")), 1)

    def test_declining_the_summary_changes_nothing(self):
        term, _ = scripted_terminal("", "", "", "", "n")

        with self.assertRaisesRegex(ByteGuardError, "Nothing was changed"):
            gather(term)

    def test_input_that_ends_early_is_an_error_not_a_default(self):
        term, _ = scripted_terminal("")

        with self.assertRaises(ByteGuardError):
            gather(term)


if __name__ == "__main__":
    unittest.main()
