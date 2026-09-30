"""Running system commands."""

import os
import subprocess

from byteguard.errors import ByteGuardError


def run(cmd, *, input=None, check=True, env=None, capture=True):
    """Run a command and return the completed process.

    Secrets are never passed as arguments, so a failure can quote the command.
    `env` adds to the environment. With `capture` off the command talks to
    the terminal directly, for the ones that show the user something to do.
    """
    environment = {**os.environ, **env} if env else None
    try:
        result = subprocess.run(cmd, input=input, capture_output=capture, text=True, env=environment)
    except FileNotFoundError:
        raise ByteGuardError(f"`{cmd[0]}` is not installed.") from None
    if check and result.returncode != 0:
        detail = ((result.stderr or result.stdout) or "").strip()
        raise ByteGuardError(f"`{' '.join(cmd)}` failed: {detail}")
    return result
