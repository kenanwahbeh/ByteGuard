"""Finding the network card and the public address to suggest during setup."""

import ipaddress
import re
import socket
import urllib.request

ADDRESS_SERVICES = ("https://api.ipify.org", "https://icanhazip.com")

HOSTNAME_RE = re.compile(
    r"(?=.{1,253}$)([A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}"
)


def default_interface(run) -> str | None:
    """The network card the default route goes out of."""
    fields = run(["ip", "-4", "route", "show", "default"], check=False).stdout.split()
    if "dev" in fields[:-1]:
        return fields[fields.index("dev") + 1]
    return None


def interfaces(run) -> dict[str, str]:
    """Network cards with a global IPv4 address, as {name: address}."""
    found = {}
    output = run(["ip", "-4", "-o", "addr", "show", "scope", "global"], check=False).stdout
    for line in output.splitlines():
        fields = line.split()
        if len(fields) >= 4 and fields[2] == "inet":
            found.setdefault(fields[1], fields[3].split("/")[0])
    return found


def _fetch(url: str) -> str:
    with urllib.request.urlopen(url, timeout=5) as response:
        return response.read(64).decode().strip()


def public_address(fetch=_fetch) -> str | None:
    for url in ADDRESS_SERVICES:
        try:
            value = fetch(url)
            ipaddress.IPv4Address(value)
        except (OSError, ValueError):
            continue
        return value
    return None


def valid_endpoint(value: str) -> bool:
    """True for an IP address or a host name that devices can be told to connect to."""
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return bool(HOSTNAME_RE.fullmatch(value))
    return True


def port_is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        try:
            sock.bind(("0.0.0.0", port))
        except OSError:
            return False
    return True
