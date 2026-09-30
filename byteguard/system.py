"""Running system commands."""

import subprocess

from byteguard.errors import ByteGuardError


def run(cmd, *, input=None, check=True):
    """Run a command and return the completed process.

    Secrets are never passed as arguments, so a failure can quote the command.
    """
    try:
        result = subprocess.run(cmd, input=input, capture_output=True, text=True)
    except FileNotFoundError:
        raise ByteGuardError(f"`{cmd[0]}` is not installed.") from None
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise ByteGuardError(f"`{' '.join(cmd)}` failed: {detail}")
    return result
