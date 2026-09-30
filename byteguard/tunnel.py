"""A Cloudflare Tunnel of its own for the web interface.

ByteGuard never touches a cloudflared that is already on the server: its
tunnel has its own name, its own files and its own service.
"""

import json
import secrets
import shutil
import socket
import tempfile
import urllib.request
from pathlib import Path

from byteguard.errors import ByteGuardError

DOH = "https://cloudflare-dns.com/dns-query?name={name}&type=NS"
NS_RECORD = 2
DEB = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-{arch}.deb"
ARCHITECTURES = {"amd64", "arm64", "armhf", "386"}


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


def install(run, download=urllib.request.urlretrieve) -> None:
    arch = run(["dpkg", "--print-architecture"]).stdout.strip()
    if arch not in ARCHITECTURES:
        raise ByteGuardError(f"Cloudflare publishes no cloudflared package for {arch}. Install it by hand first.")
    with tempfile.TemporaryDirectory() as folder:
        package = Path(folder) / "cloudflared.deb"
        try:
            download(DEB.format(arch=arch), package)
        except OSError:
            raise ByteGuardError("Could not download cloudflared from GitHub.") from None
        run(["dpkg", "-i", str(package)])


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
