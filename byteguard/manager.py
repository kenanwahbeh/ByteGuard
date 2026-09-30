"""Everything ByteGuard can do to the server. The terminal and the web interface both call this."""

import contextlib
import copy
import datetime
import ipaddress
import shutil
import tempfile

from byteguard import backup, firewall, state, system, telegram, wg
from byteguard.errors import ByteGuardError
from byteguard.paths import INTERFACE, Paths
from byteguard.web import auth

DEFAULT_SUBNET = "10.66.66.0/24"
MTU = 1420
KEEPALIVE = 25
DNS = ["1.1.1.1", "1.0.0.1"]

SERVICE = f"wg-quick@{INTERFACE}"
UI_SERVICE = "byteguard-ui"
DEFAULT_UI_PORT = 51821

# Root, but with nothing beyond managing the VPN interface, and a read-only
# system apart from ByteGuard's own files.
UI_UNIT = """\
[Unit]
Description=ByteGuard web interface
After={service}.service network-online.target
Wants={service}.service

[Service]
ExecStart={launcher} serve
Restart=on-failure
RestartSec=3
CapabilityBoundingSet=CAP_NET_ADMIN
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths={etc} {wireguard} {backups}
ProtectHome=true
PrivateTmp=true
PrivateDevices=true
ProtectKernelModules=true
ProtectKernelTunables=true
ProtectControlGroups=true
RestrictSUIDSGID=true
LockPersonality=true
MemoryMax=200M

[Install]
WantedBy=multi-user.target
"""


class Manager:
    def __init__(self, paths: Paths | None = None, run=system.run, send=telegram.send_document):
        self.paths = paths or Paths()
        self.run = run
        self.send = send
        # What the backup after the latest change did, per destination.
        self.last_backup: dict = {}

    def _save(self, data: dict) -> None:
        """Save the state, then back it up. A failed backup never undoes the change."""
        state.save(self.paths.state, data)
        try:
            self.last_backup = backup.run(self.paths, data, self.send)
        except (OSError, ValueError) as error:
            self.last_backup = {"local": {"ok": False, "error": str(error)}}

    def back_up(self) -> dict:
        with state.locked(self.paths.lock):
            self._save(self._state())
        return self.last_backup

    def telegram_chat(self) -> dict | None:
        return self._state().get("backup", {}).get("telegram")

    def set_telegram(self, token: str | None, chat_id: int | None = None) -> None:
        """Send every backup to this Telegram chat, or stop with token None."""
        with state.locked(self.paths.lock):
            data = self._state()
            destinations = data.setdefault("backup", {})
            if token is None:
                destinations.pop("telegram", None)
            else:
                destinations["telegram"] = {"token": token, "chat_id": chat_id}
            self._save(data)

    # Reading

    def is_set_up(self) -> bool:
        return state.load(self.paths.state) is not None

    def _state(self) -> dict:
        data = state.load(self.paths.state)
        if data is None:
            raise ByteGuardError("This server is not set up yet. Run `sudo byteguard setup`.")
        return data

    def server(self) -> dict:
        return self._state()["server"]

    def devices(self) -> list[dict]:
        return self._state()["devices"]

    def client_config(self, name: str) -> str:
        data = self._state()
        return wg.client_config(data, _find(data, name))

    def qr_svg(self, name: str) -> str:
        """The device's configuration as a QR code image for the web interface."""
        return self.run(["qrencode", "-t", "SVG", "-o", "-"], input=self.client_config(name)).stdout

    def state_for_backup(self) -> dict:
        return self._state()

    def ui(self) -> dict | None:
        """The web interface's settings, or None when it is off."""
        return self._state().get("ui")

    def enable_ui(self, password: str, port: int = DEFAULT_UI_PORT) -> str:
        """Turn the web interface on, reachable only from inside the VPN. Returns its address."""
        if len(password) < auth.MIN_PASSWORD_LENGTH:
            raise ByteGuardError(f"The password needs at least {auth.MIN_PASSWORD_LENGTH} characters.")
        with state.locked(self.paths.lock):
            data = self._state()
            previous = data.get("ui")
            if previous and previous["port"] != port:
                firewall.close_ui(self.run, data["firewall"]["mode"], previous["port"])
            data["ui"] = {"port": port, "password": auth.hash_password(password)}
            self._start_ui(data)
            self._save(data)
            return f"http://{data['server']['address']}:{port}"

    def disable_ui(self) -> None:
        with state.locked(self.paths.lock):
            data = self._state()
            self._stop_ui(data)
            data.pop("ui", None)
            state.write_private(self.paths.wg_conf, wg.server_config(data))
            self._save(data)

    def _start_ui(self, data: dict) -> None:
        firewall.open_ui(self.run, data["firewall"]["mode"], data["ui"]["port"])
        # The rule is also an interface hook, so it returns after a reboot.
        state.write_private(self.paths.wg_conf, wg.server_config(data))
        self.paths.ui_unit.parent.mkdir(parents=True, exist_ok=True)
        self.paths.ui_unit.write_text(
            UI_UNIT.format(
                service=SERVICE,
                launcher=self.paths.launcher,
                etc=self.paths.etc,
                wireguard=self.paths.wireguard,
                backups=self.paths.backups,
            )
        )
        self.paths.backups.mkdir(parents=True, exist_ok=True)
        self.run(["systemctl", "daemon-reload"])
        self.run(["systemctl", "enable", UI_SERVICE])
        # Restart, so a changed password ends every open session.
        self.run(["systemctl", "restart", UI_SERVICE])

    def _stop_ui(self, data: dict) -> None:
        if "ui" not in data:
            return
        self.run(["systemctl", "disable", "--now", UI_SERVICE], check=False)
        self.paths.ui_unit.unlink(missing_ok=True)
        self.run(["systemctl", "daemon-reload"], check=False)
        firewall.close_ui(self.run, data["firewall"]["mode"], data["ui"]["port"])

    def qr_code(self, name: str) -> str:
        """The device's configuration as a QR code drawn with terminal characters."""
        return self.run(["qrencode", "-t", "ansiutf8"], input=self.client_config(name)).stdout

    def status(self) -> list[dict]:
        """Every device with its live connection figures, which reset when the interface restarts."""
        data = self._state()
        dump = self.run(["wg", "show", INTERFACE, "dump"], check=False)
        live = wg.parse_dump(dump.stdout) if dump.returncode == 0 else {}
        idle = {"endpoint": None, "last_handshake": None, "online": False, "received": 0, "sent": 0}
        return [
            {
                "name": device["name"],
                "address": device["address"],
                "enabled": device["enabled"],
                **live.get(device["public_key"], idle),
            }
            for device in data["devices"]
        ]

    # Setting up and removing

    def check_can_set_up(self) -> None:
        if self.is_set_up():
            raise ByteGuardError("This server is already set up. Run `sudo byteguard` to manage it.")
        if self.paths.wg_conf.exists():
            raise ByteGuardError(
                f"{self.paths.wg_conf} already exists and was not created by ByteGuard. "
                "Move it away first; ByteGuard will not overwrite another WireGuard setup."
            )

    def set_up(self, *, iface: str, endpoint: str, port: int, subnet: str = DEFAULT_SUBNET) -> None:
        network = check_subnet(subnet)
        with state.locked(self.paths.lock):
            self.check_can_set_up()
            private, public = wg.keypair(self.run)
            data = {
                "schema": state.SCHEMA,
                "server": {
                    "private_key": private,
                    "public_key": public,
                    "iface": iface,
                    "endpoint": endpoint,
                    "port": port,
                    "subnet": str(network),
                    # The server takes the first address; devices follow it.
                    "address": str(next(network.hosts())),
                    "mtu": MTU,
                    "keepalive": KEEPALIVE,
                    "dns": DNS,
                },
                "firewall": {"mode": firewall.detect(self.run)},
                "devices": [],
            }
            self._bring_up(data)

    def restore(self, saved: dict, *, iface: str, endpoint: str | None = None) -> None:
        """Set this server up from a backup's state: same keys, same devices."""
        with state.locked(self.paths.lock):
            self.check_can_set_up()
            data = copy.deepcopy(saved)
            data["server"]["iface"] = iface
            if endpoint:
                data["server"]["endpoint"] = endpoint
            # The new server may not have the firewall the old one had.
            data["firewall"] = {"mode": firewall.detect(self.run)}
            self._bring_up(data)

    def _bring_up(self, data: dict) -> None:
        server = data["server"]
        try:
            firewall.enable_forwarding(self.paths.sysctl, self.run)
            firewall.open_ports(self.run, data["firewall"]["mode"], server["iface"], server["port"])
            state.write_private(self.paths.wg_conf, wg.server_config(data))
            self.run(["systemctl", "enable", "--now", SERVICE])
            if "ui" in data:
                self._start_ui(data)
        except BaseException:
            # Leave the server as it was found, so this can simply be run again.
            self._tear_down(data)
            raise
        self._save(data)

    def uninstall(self) -> None:
        """Remove the VPN, its firewall rules, its keys and the program itself."""
        with state.locked(self.paths.lock):
            data = state.load(self.paths.state)
            if data is not None:
                self._tear_down(data)
        shutil.rmtree(self.paths.etc, ignore_errors=True)
        shutil.rmtree(self.paths.program, ignore_errors=True)
        self.paths.launcher.unlink(missing_ok=True)

    def _tear_down(self, data: dict) -> None:
        server = data["server"]
        self._stop_ui(data)
        # Stopping the interface runs PostDown, which removes its iptables rules.
        self.run(["systemctl", "disable", "--now", SERVICE], check=False)
        firewall.close_ports(self.run, data["firewall"]["mode"], server["iface"], server["port"])
        self.paths.wg_conf.unlink(missing_ok=True)
        # Forwarding itself stays on: other software on the host, Docker for
        # one, depends on it.
        self.paths.sysctl.unlink(missing_ok=True)

    def set_port(self, port: int) -> None:
        """Move the VPN to another UDP port. Every device then needs its configuration again."""
        if not 1 <= port <= 65535:
            raise ByteGuardError("The port has to be between 1 and 65535.")
        with state.locked(self.paths.lock):
            data = self._state()
            server, mode = data["server"], data["firewall"]["mode"]
            old = server["port"]
            if port == old:
                return
            # Stop first: PostDown has to run against the configuration that
            # still names the old port.
            self.run(["systemctl", "stop", SERVICE])
            try:
                self._move_port(data, old, port)
            except BaseException:
                self._move_port(data, port, old)
                raise

    def _move_port(self, data: dict, old: int, new: int) -> None:
        server, mode = data["server"], data["firewall"]["mode"]
        firewall.close_ports(self.run, mode, server["iface"], old)
        server["port"] = new
        firewall.open_ports(self.run, mode, server["iface"], new)
        state.write_private(self.paths.wg_conf, wg.server_config(data))
        self.run(["systemctl", "start", SERVICE])
        self._save(data)

    # Devices

    def add_device(self, name: str) -> dict:
        wg.check_name(name)
        with self._changing() as data:
            if any(device["name"] == name for device in data["devices"]):
                raise ByteGuardError(f"A device named {name!r} already exists.")
            private, public = wg.keypair(self.run)
            device = {
                "name": name,
                "private_key": private,
                "public_key": public,
                "preshared_key": wg.preshared_key(self.run),
                "address": wg.next_address(
                    data["server"]["subnet"],
                    data["server"]["address"],
                    (other["address"] for other in data["devices"]),
                ),
                "enabled": True,
                "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
            }
            data["devices"].append(device)
        return device

    def remove_device(self, name: str) -> None:
        with self._changing() as data:
            data["devices"].remove(_find(data, name))

    def set_enabled(self, name: str, enabled: bool) -> None:
        with self._changing() as data:
            _find(data, name)["enabled"] = enabled

    @contextlib.contextmanager
    def _changing(self):
        """Load the state for a change, then save it and apply it to the running interface."""
        with state.locked(self.paths.lock):
            data = self._state()
            yield data
            self._save(data)
            state.write_private(self.paths.wg_conf, wg.server_config(data))
            self._sync()

    def _sync(self) -> None:
        """Apply the configuration file to the running interface without dropping connections."""
        if self.run(["wg", "show", INTERFACE], check=False).returncode != 0:
            # The interface is down; it reads the file when it next starts.
            return
        stripped = self.run(["wg-quick", "strip", str(self.paths.wg_conf)]).stdout
        # Ubuntu's AppArmor profile lets `wg` read files under /etc/wireguard only.
        with tempfile.NamedTemporaryFile("w", dir=self.paths.wireguard, prefix=".sync-") as handle:
            handle.write(stripped)
            handle.flush()
            self.run(["wg", "syncconf", INTERFACE, handle.name])


def check_subnet(subnet: str) -> ipaddress.IPv4Network:
    """The VPN's own network: private IPv4 with room for the server and at least one device."""
    try:
        network = ipaddress.IPv4Network(subnet, strict=False)
    except ValueError:
        raise ByteGuardError(f"{subnet!r} is not an IPv4 network such as {DEFAULT_SUBNET}.") from None
    if not network.is_private or network.prefixlen > 30:
        raise ByteGuardError("The VPN network has to be a private range of /30 or larger.")
    return network


def _find(data: dict, name: str) -> dict:
    for device in data["devices"]:
        if device["name"] == name:
            return device
    raise ByteGuardError(f"There is no device named {name!r}.")
