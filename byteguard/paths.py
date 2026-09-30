"""Where ByteGuard keeps its files. Tests point these at a temporary directory."""

from dataclasses import dataclass
from pathlib import Path

INTERFACE = "wg0"


@dataclass(frozen=True)
class Paths:
    etc: Path = Path("/etc/byteguard")
    wireguard: Path = Path("/etc/wireguard")
    sysctl: Path = Path("/etc/sysctl.d/99-byteguard.conf")
    program: Path = Path("/opt/byteguard")
    launcher: Path = Path("/usr/local/bin/byteguard")
    backups: Path = Path("/var/backups/byteguard")
    ui_unit: Path = Path("/etc/systemd/system/byteguard-ui.service")
    tunnel_unit: Path = Path("/etc/systemd/system/byteguard-tunnel.service")

    @property
    def state(self) -> Path:
        return self.etc / "state.json"

    @property
    def lock(self) -> Path:
        return self.etc / "state.lock"

    @property
    def backup_status(self) -> Path:
        return self.etc / "backup-status.json"

    @property
    def tunnel_dir(self) -> Path:
        """The UI tunnel's own cloudflared files, apart from any other cloudflared on the host."""
        return self.etc / "cloudflared"

    @property
    def wg_conf(self) -> Path:
        return self.wireguard / f"{INTERFACE}.conf"
