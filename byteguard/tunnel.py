"""A Cloudflare Tunnel of its own for the web interface.

ByteGuard never touches a cloudflared that is already on the server: its
tunnel has its own name, its own files and its own service.
"""

import hashlib
import json
import secrets
import shutil
import socket
import urllib.request
from pathlib import Path

from byteguard.errors import ByteGuardError

DOH = "https://cloudflare-dns.com/dns-query?name={name}&type=NS"
NS_RECORD = 2
# Cloudflare's signed package repository. The key is pinned by its
# fingerprint, so a key swapped on the way, or on the server, is refused.
APT_KEY_URL = "https://pkg.cloudflare.com/cloudflare-main.gpg"
APT_KEY_FINGERPRINT = "CC94B39C77AE7342A68B89628A682D308D4E5E73"
APT_REPOSITORY = "https://pkg.cloudflare.com/cloudflared"
APT_KEYRING = Path("/etc/apt/keyrings/byteguard-cloudflare.gpg")
APT_SOURCES = Path("/etc/apt/sources.list.d")
APT_SOURCE_NAME = "byteguard-cloudflared.list"


def _nameservers(name: str) -> list[str]:
    request = urllib.request.Request(DOH.format(name=name), headers={"Accept": "application/dns-json"})
    with urllib.request.urlopen(request, timeout=10) as response:
        answer = json.loads(response.read())
    return [record["data"].rstrip(".").lower() for record in answer.get("Answer", []) if record["type"] == NS_RECORD]


def zone_of(hostname: str, lookup=_nameservers) -> tuple[str, list[str]]:
    """The domain that holds `hostname` and its name servers.

    Walks up from the host name until a name has name servers of its own,
    which also gets domains like example.co.uk right.
    """
    labels = hostname.lower().rstrip(".").split(".")
    for start in range(len(labels) - 1):
        name = ".".join(labels[start:])
        try:
            servers = lookup(name)
        except (OSError, ValueError):
            raise ByteGuardError("Could not look the domain up. Check the server's internet connection.") from None
        if servers:
            return name, servers
    raise ByteGuardError(f"No domain was found for {hostname}. Check the spelling.")


def on_cloudflare(servers: list[str]) -> bool:
    return bool(servers) and all(server.endswith(".ns.cloudflare.com") for server in servers)


def installed(run) -> bool:
    try:
        return run(["cloudflared", "--version"], check=False).returncode == 0
    except ByteGuardError:
        return False


def other_tunnel_running(run) -> bool:
    """True when the server already runs a cloudflared that is not ByteGuard's."""
    return run(["systemctl", "is-active", "--quiet", "cloudflared"], check=False).returncode == 0


def _fetch(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=30) as response:
        return response.read(1024 * 1024)


def key_fingerprint(key: bytes) -> str:
    """The OpenPGP v4 fingerprint of the first public key in a binary keyring."""
    try:
        tag = key[0]
        if not tag & 0x80:
            raise ValueError
        if tag & 0x40:
            packet, size = tag & 0x3F, key[1]
            if size < 192:
                start, length = 2, size
            elif size < 224:
                start, length = 3, ((size - 192) << 8) + key[2] + 192
            elif size == 255:
                start, length = 6, int.from_bytes(key[2:6], "big")
            else:
                raise ValueError
        else:
            packet, width = (tag >> 2) & 0x0F, {0: 1, 1: 2, 2: 4}[tag & 3]
            start, length = 1 + width, int.from_bytes(key[1 : 1 + width], "big")
        body = key[start : start + length]
        if packet != 6 or len(body) != length or body[0] != 4:
            raise ValueError
    except (IndexError, KeyError, ValueError):
        return ""
    return hashlib.sha1(b"\x99" + len(body).to_bytes(2, "big") + body).hexdigest().upper()


def install(run, fetch=_fetch, keyring: Path = APT_KEYRING, sources: Path = APT_SOURCES) -> None:
    """Install cloudflared from Cloudflare's signed apt repository, so apt also keeps it updated."""
    listed = [*sources.glob("*.list"), *sources.glob("*.sources")]
    if not any(APT_REPOSITORY in path.read_text() for path in listed):
        try:
            key = fetch(APT_KEY_URL)
        except OSError:
            raise ByteGuardError("Could not download Cloudflare's package key.") from None
        if key_fingerprint(key) != APT_KEY_FINGERPRINT:
            raise ByteGuardError(
                "Cloudflare's package key is not the expected one, so nothing was installed. "
                "Install cloudflared by hand from https://pkg.cloudflare.com and run this again."
            )
        keyring.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
        keyring.write_bytes(key)
        keyring.chmod(0o644)
        source = sources / APT_SOURCE_NAME
        source.write_text(f"deb [signed-by={keyring}] {APT_REPOSITORY} any main\n")
    run(["apt-get", "update", "-qq"])
    run(["apt-get", "install", "-y", "-qq", "cloudflared"], env={"DEBIAN_FRONTEND": "noninteractive"})


def create(run, home: Path, hostname: str) -> dict:
    """Sign in to Cloudflare, create a tunnel and point `hostname` at it.

    Returns {"id", "name", "credentials"}. `home` is a scratch folder that is
    deleted before returning, and with it the sign-in certificate, which can
    manage the whole domain. Only the tunnel's own credentials are kept.
    """
    home.mkdir(mode=0o700, parents=True, exist_ok=True)
    env = {"HOME": str(home)}
    credentials = home / "new-tunnel.json"
    name = f"byteguard-{socket.gethostname()}-{secrets.token_hex(2)}"
    try:
        # Prints a link to open in a browser and waits for the approval.
        run(["cloudflared", "tunnel", "login"], env=env, capture=False)
        run(["cloudflared", "tunnel", "create", "--credentials-file", str(credentials), name], env=env)
        created = json.loads(credentials.read_text())
        routed = run(["cloudflared", "tunnel", "route", "dns", created["TunnelID"], hostname], env=env, check=False)
        if routed.returncode != 0:
            # Do not leave a tunnel behind that nothing will ever run.
            run(["cloudflared", "tunnel", "delete", created["TunnelID"]], env=env, check=False)
            detail = (routed.stderr or routed.stdout).strip().splitlines()[-1:]
            raise ByteGuardError(
                f"Cloudflare would not point {hostname} at the tunnel: {' '.join(detail)} "
                "If a DNS record with that name already exists, delete it or choose another name."
            )
        return {"id": created["TunnelID"], "name": name, "credentials": created}
    finally:
        shutil.rmtree(home, ignore_errors=True)


def config(tunnel_id: str, credentials_file: Path, hostname: str, target: str) -> str:
    return (
        f"tunnel: {tunnel_id}\n"
        f"credentials-file: {credentials_file}\n"
        "ingress:\n"
        f"  - hostname: {hostname}\n"
        f"    service: {target}\n"
        "  - service: http_status:404\n"
    )
