"""Letting VPN traffic through the host firewall without disturbing what is already there.

Every rule is added next to the existing ones and removed again by its exact
text. Nothing here flushes a chain, changes a policy or turns forwarding off.
"""

from pathlib import Path

from byteguard.errors import ByteGuardError
from byteguard.paths import INTERFACE

UFW = "ufw"
IPTABLES = "iptables"

SYSCTL_TEXT = (
    "# Written by ByteGuard: the VPN server forwards its devices' traffic.\n"
    "net.ipv4.ip_forward = 1\n"
)


def detect(run) -> str:
    """Return UFW when ufw is managing the firewall, IPTABLES otherwise."""
    try:
        status = run(["ufw", "status"], check=False).stdout
    except ByteGuardError:
        # ufw is not installed.
        return IPTABLES
    return UFW if "Status: active" in status else IPTABLES


def hooks(mode: str, iface: str, port: int, subnet: str) -> tuple[list[str], list[str]]:
    """The wg-quick PostUp and PostDown commands for this firewall mode.

    With ufw the port and the forwarding are ufw rules (see `open_ports`), so
    only the address translation lives here. Without it, the rules are
    inserted ahead of whatever else is in the chain, because Docker leaves
    the FORWARD policy at DROP.
    """
    rules = [("-t nat -A POSTROUTING", "-t nat -D POSTROUTING", f"-s {subnet} -o {iface} -j MASQUERADE")]
    if mode == IPTABLES:
        rules += [
            ("-I INPUT", "-D INPUT", f"-p udp --dport {port} -j ACCEPT"),
            ("-I FORWARD", "-D FORWARD", "-i %i -j ACCEPT"),
            ("-I FORWARD", "-D FORWARD", "-o %i -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT"),
        ]
    up = [f"iptables -w {add} {spec}" for add, _, spec in rules]
    down = [f"iptables -w {remove} {spec}" for _, remove, spec in rules]
    return up, down


def _ufw_rules(iface: str, port: int) -> list[list[str]]:
    return [
        ["allow", f"{port}/udp"],
        ["route", "allow", "in", "on", INTERFACE, "out", "on", iface],
    ]


def open_ports(run, mode: str, iface: str, port: int) -> None:
    if mode != UFW:
        return
    for rule in _ufw_rules(iface, port):
        run(["ufw", *rule, "comment", "ByteGuard"])


def close_ports(run, mode: str, iface: str, port: int) -> None:
    if mode != UFW:
        return
    for rule in _ufw_rules(iface, port):
        # `ufw route delete allow ...`, but `ufw delete allow ...`.
        position = 1 if rule[0] == "route" else 0
        run(["ufw", *rule[:position], "delete", *rule[position:]], check=False)


def enable_forwarding(sysctl_path: Path, run) -> None:
    sysctl_path.parent.mkdir(parents=True, exist_ok=True)
    sysctl_path.write_text(SYSCTL_TEXT)
    run(["sysctl", "-q", "-w", "net.ipv4.ip_forward=1"])
