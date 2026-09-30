"""Stand-ins for the system, so the tests never touch the real network or firewall."""

import shutil
import subprocess
import tempfile
from pathlib import Path

from byteguard.errors import ByteGuardError
from byteguard.paths import Paths
from byteguard.prompt import Terminal


class FakeRun:
    """Records every command and answers the ones ByteGuard reads output from."""

    def __init__(self, *, interface_up=True, outputs=None, failing=(), missing=(), active=()):
        self.calls = []
        # Services that `systemctl is-active` reports as running.
        self.active = set(active)
        self.missing = set(missing)
        self.interface_up = interface_up
        self.outputs = dict(outputs or {})
        self.failing = set(failing)
        self._keys = 0

    def __call__(self, cmd, *, input=None, check=True, env=None, capture=True):
        cmd = list(cmd)
        if cmd[0] in self.missing:
            raise ByteGuardError(f"`{cmd[0]}` is not installed.")
        self.calls.append(cmd)
        joined = " ".join(cmd)
        code, out = 0, self.outputs.get(joined, "")
        if cmd[:2] == ["wg", "genkey"]:
            self._keys += 1
            out = f"private-{self._keys}\n"
        elif cmd[:2] == ["wg", "pubkey"]:
            out = f"public-of-{input.strip()}\n"
        elif cmd[:2] == ["wg", "genpsk"]:
            self._keys += 1
            out = f"psk-{self._keys}\n"
        elif cmd == ["wg", "show", "wg0"] and not self.interface_up:
            code = 1
        elif cmd[:3] == ["systemctl", "is-active", "--quiet"]:
            code = 0 if cmd[3] in self.active else 3
        if joined in self.failing:
            code = 1
        if check and code:
            raise ByteGuardError(f"`{joined}` failed")
        return subprocess.CompletedProcess(cmd, code, stdout=out, stderr="")

    def ran(self, prefix: str) -> list[str]:
        """The recorded commands that start with `prefix`, each as one string."""
        commands = [" ".join(call) for call in self.calls]
        return [command for command in commands if command.startswith(prefix)]


def temp_paths(testcase) -> Paths:
    root = Path(tempfile.mkdtemp())
    testcase.addCleanup(shutil.rmtree, root, ignore_errors=True)
    return Paths(
        etc=root / "etc/byteguard",
        wireguard=root / "etc/wireguard",
        sysctl=root / "etc/sysctl.d/99-byteguard.conf",
        program=root / "opt/byteguard",
        launcher=root / "usr/local/bin/byteguard",
        backups=root / "var/backups/byteguard",
        ui_unit=root / "etc/systemd/system/byteguard-ui.service",
        tunnel_unit=root / "etc/systemd/system/byteguard-tunnel.service",
    )


def scripted_terminal(*answers):
    """A Terminal fed these answers, and the list that collects what it writes."""
    lines = iter(f"{answer}\n" for answer in answers)
    written = []
    return Terminal(lambda: next(lines, ""), written.append), written
