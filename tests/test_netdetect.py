import unittest

from byteguard import netdetect
from fakes import FakeRun

ROUTE = "ip -4 route show default"
ADDRESSES = "ip -4 -o addr show scope global"


class DefaultInterfaceTest(unittest.TestCase):
    def test_it_is_the_card_the_default_route_uses(self):
        run = FakeRun(outputs={ROUTE: "default via 203.0.113.1 dev ens3 proto dhcp src 203.0.113.7 metric 100\n"})

        self.assertEqual(netdetect.default_interface(run), "ens3")

    def test_no_default_route_means_no_answer(self):
        self.assertIsNone(netdetect.default_interface(FakeRun()))


class InterfacesTest(unittest.TestCase):
    def test_each_card_is_listed_once_with_its_first_address(self):
        run = FakeRun(
            outputs={
                ADDRESSES: (
                    "2: ens3    inet 203.0.113.7/26 metric 100 brd 203.0.113.63 scope global dynamic ens3\\\n"
                    "2: ens3    inet 203.0.113.8/26 scope global secondary ens3\\\n"
                    "3: docker0    inet 172.17.0.1/16 brd 172.17.255.255 scope global docker0\\\n"
                )
            }
        )

        self.assertEqual(netdetect.interfaces(run), {"ens3": "203.0.113.7", "docker0": "172.17.0.1"})


class PublicAddressTest(unittest.TestCase):
    def test_the_first_service_that_answers_with_an_address_wins(self):
        self.assertEqual(netdetect.public_address(lambda url: "203.0.113.7"), "203.0.113.7")

    def test_a_service_that_fails_or_answers_nonsense_is_skipped(self):
        answers = iter([OSError("unreachable"), "198.51.100.9"])

        def fetch(url):
            answer = next(answers)
            if isinstance(answer, Exception):
                raise answer
            return answer

        self.assertEqual(netdetect.public_address(fetch), "198.51.100.9")

    def test_no_answer_at_all_is_none(self):
        self.assertIsNone(netdetect.public_address(lambda url: "<html>blocked</html>"))


class EndpointTest(unittest.TestCase):
    def test_addresses_and_host_names_are_valid(self):
        for value in ("203.0.113.7", "2001:db8::7", "vpn.example.com", "a-b.example.co.uk"):
            self.assertTrue(netdetect.valid_endpoint(value), value)

    def test_anything_else_is_not(self):
        for value in ("", "localhost", "vpn example.com", "http://vpn.example.com", "example.com:51820"):
            self.assertFalse(netdetect.valid_endpoint(value), value)


if __name__ == "__main__":
    unittest.main()
