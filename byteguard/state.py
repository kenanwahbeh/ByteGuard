"""The state file: server keys, settings and devices, as JSON readable only by root."""

import contextlib
import fcntl
import json
import os
import tempfile
from pathlib import Path

from byteguard.errors import ByteGuardError

SCHEMA = 1


def write_private(path: Path, text: str) -> None:
    """Replace `path` atomically with a file only its owner can read."""
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    # mkstemp creates the file with mode 0600.
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}-")
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp)
        raise


def load(path: Path) -> dict | None:
    try:
        text = path.read_text()
    except FileNotFoundError:
        return None
    data = json.loads(text)
    if data.get("schema") != SCHEMA:
        raise ByteGuardError(
            f"{path} was written by a different ByteGuard version "
            f"(schema {data.get('schema')}, expected {SCHEMA})."
        )
    return data


def save(path: Path, data: dict) -> None:
    write_private(path, json.dumps(data, indent=2) + "\n")


@contextlib.contextmanager
def locked(lock_path: Path):
    """Hold the state lock, so the terminal and the web interface never interleave writes."""
    lock_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with open(lock_path, "w") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield
