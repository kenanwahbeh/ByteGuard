import unittest

from byteguard import firewall, wg
from byteguard.errors import ByteGuardError


def sample_state(mode=firewall.UFW):
    return {
        "server": {
            "private_key": "server-private",
            "public_key": "server-public",
            "iface": "eth0",
            "endpoint": "203.0.113.7",
            "port": 51820,
            "subnet": "10.66.66.0/24",
            "address": "10.66.66.1",
            "mtu": 1420,
            "keepalive": 25,
            "dns": ["1.1.1.1", "1.0.0.1"],
        },
        "firewall": {"mode": mode},
        "devices": [
            {
                "name": "phone",
                "private_key": "phone-private",
                "public_key": "phone-public",
                "preshared_key": "phone-psk",
                "address": "10.66.66.2",
                "enabled": True,
            },
            {
                "name": "laptop",
                "private_key": "laptop-private",
                "public_key": "laptop-public",
                "preshared_key": "laptop-psk",
                "address": "10.66.66.3",
                "enabled": False,
            },
        ],
    }


class AddressTest(unittest.TestCase):
    def test_the_first_device_gets_the_address_after_the_server(self):
        self.assertEqual(wg.next_address("10.66.66.0/24", "10.66.66.1", []), "10.66.66.2")

    def test_an_address_freed_by_a_removed_device_is_reused(self):
        used = ["10.66.66.2", "10.66.66.4"]

        self.assertEqual(wg.next_address("10.66.66.0/24", "10.66.66.1", used), "10.66.66.3")

    def test_a_full_subnet_is_an_error(self):
        with self.assertRaises(ByteGuardError):
            wg.next_address("10.66.66.0/30", "10.66.66.1", ["10.66.66.2"])


class NameTest(unittest.TestCase):
    def test_ordinary_names_are_accepted(self):
        for name in ("phone", "Kinan-Laptop", "tv_2", "a" * 32):
            wg.check_name(name)

    def test_names_that_could_break_a_config_file_are_refused(self):
        for name in ("", "-phone", "my phone", "phone\n[Peer]", "a" * 33, "هاتف"):
            with self.subTest(name=name), self.assertRaises(ByteGuardError):
                wg.check_name(name)


class ServerConfigTest(unittest.TestCase):
    def test_it_describes_the_interface(self):
        config = wg.server_config(sample_state())

        self.assertIn("Address = 10.66.66.1/24\n", config)
        self.assertIn("ListenPort = 51820\n", config)
        self.assertIn("PrivateKey = server-private\n", config)
        self.assertIn("MTU = 1420\n", config)

    def test_it_never_asks_wg_quick_to_change_the_servers_dns_or_save_itself(self):
        config = wg.server_config(sample_state())

        self.assertNotIn("DNS", config)
        self.assertNotIn("SaveConfig", config)

    def test_an_enabled_device_is_a_peer_limited_to_its_own_address(self):
        config = wg.server_config(sample_state())

        self.assertIn(
            "# phone\n[Peer]\nPublicKey = phone-public\nPresharedKey = phone-psk\n"
            "AllowedIPs = 10.66.66.2/32\n",
            config,
        )

    def test_a_disabled_device_is_left_out(self):
        self.assertNotIn("laptop", wg.server_config(sample_state()))

    def test_device_private_keys_never_reach_the_server_config(self):
        self.assertNotIn("phone-private", wg.server_config(sample_state()))


class ClientConfigTest(unittest.TestCase):
    def setUp(self):
        self.state = sample_state()
        self.config = wg.client_config(self.state, self.state["devices"][0])

    def test_it_sends_all_traffic_through_the_server(self):
        self.assertIn("AllowedIPs = 0.0.0.0/0, ::/0\n", self.config)

    def test_it_carries_the_agreed_keepalive_and_mtu(self):
        self.assertIn("PersistentKeepalive = 25\n", self.config)
        self.assertIn("MTU = 1420\n", self.config)

    def test_it_points_at_the_server(self):
        self.assertIn("PublicKey = server-public\n", self.config)
        self.assertIn("Endpoint = 203.0.113.7:51820\n", self.config)

    def test_an_ipv6_endpoint_is_bracketed(self):
        self.state["server"]["endpoint"] = "2001:db8::7"

        config = wg.client_config(self.state, self.state["devices"][0])

        self.assertIn("Endpoint = [2001:db8::7]:51820\n", config)


class DumpTest(unittest.TestCase):
    DUMP = (
        "server-private\tserver-public\t51820\toff\n"
        "phone-public\tphone-psk\t198.51.100.4:40000\t10.66.66.2/32\t1000\t2048\t4096\t25\n"
        "laptop-public\tlaptop-psk\t(none)\t10.66.66.3/32\t0\t0\t0\toff\n"
    )

    def test_a_recent_handshake_means_online(self):
        peers = wg.parse_dump(self.DUMP, now=1100)

        self.assertTrue(peers["phone-public"]["online"])
        self.assertEqual(peers["phone-public"]["received"], 2048)
        self.assertEqual(peers["phone-public"]["sent"], 4096)
        self.assertEqual(peers["phone-public"]["endpoint"], "198.51.100.4:40000")

    def test_an_old_handshake_means_offline_but_still_seen(self):
        phone = wg.parse_dump(self.DUMP, now=1000 + wg.ONLINE_WINDOW_SECONDS + 1)["phone-public"]

        self.assertFalse(phone["online"])
        self.assertEqual(phone["last_handshake"], 1000)

    def test_a_device_that_never_connected_has_no_handshake(self):
        laptop = wg.parse_dump(self.DUMP, now=1100)["laptop-public"]

        self.assertFalse(laptop["online"])
        self.assertIsNone(laptop["last_handshake"])
        self.assertIsNone(laptop["endpoint"])


if __name__ == "__main__":
    unittest.main()
