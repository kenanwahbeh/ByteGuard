"""Backups: the installer with the server's state inside, so one file restores everything.

A backup is not encrypted. It holds the server's and the devices' keys and
the credentials of the places backups are sent to.
"""

import datetime
import json
import socket
from pathlib import Path

from byteguard import __version__, bundle, state, telegram
from byteguard.errors import ByteGuardError
from byteguard.paths import Paths


def file_name() -> str:
    return f"byteguard-backup-{socket.gethostname()}.sh"


def build(data: dict) -> str:
    """The backup script for this state, built from the program that is running."""
    made_at = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    payload = json.dumps({"made_at": made_at, "host": socket.gethostname(), "state": data}, indent=2)
    files = bundle.package_files(Path(__file__).resolve().parent)
    return bundle.build_installer(files, __version__, data=payload)


def read_payload(path: Path) -> dict:
    """The data a backup script handed over for restoring."""
    try:
        payload = json.loads(path.read_text())
        payload["state"]["server"]["private_key"]
    except (OSError, ValueError, KeyError, TypeError):
        raise ByteGuardError(f"{path} is not ByteGuard backup data.") from None
    if payload["state"].get("schema") != state.SCHEMA:
        raise ByteGuardError("This backup was made by a ByteGuard version this one cannot restore.")
    return payload


def run(paths: Paths, data: dict, send=telegram.send_document) -> dict:
    """Write the backup on the server and send it wherever backups are set to go.

    Returns what happened per destination and records it for the next status check.
    """
    text = build(data)
    local = paths.backups / file_name()
    state.write_private(local, text)
    results = {"local": {"ok": True, "path": str(local)}}

    chat = data.get("backup", {}).get("telegram")
    if chat:
        devices = len(data["devices"])
        caption = f"ByteGuard backup of {socket.gethostname()}: {devices} device{'s' if devices != 1 else ''}."
        try:
            send(chat["token"], chat["chat_id"], file_name(), text, caption)
            results["telegram"] = {"ok": True}
        except ByteGuardError as error:
            results["telegram"] = {"ok": False, "error": str(error)}

    made_at = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    state.write_private(paths.backup_status, json.dumps({"made_at": made_at, **results}, indent=2) + "\n")
    return results
