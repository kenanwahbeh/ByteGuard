"""Building the single installer file: the bootstrap script with the program embedded in it.

The program files go in as plain text between heredoc markers, not as a
compressed blob, so the installer can be read from top to bottom before it
is run.
"""

import re
from pathlib import Path

PAYLOAD_MARK = "# @@BYTEGUARD_PAYLOAD@@"
DATA_MARK = "# @@BYTEGUARD_DATA@@"
DATA_DELIMITER = "__BYTEGUARD_DATA_EOF__"
VERSION_MARK = "@@BYTEGUARD_VERSION@@"
DELIMITER = "__BYTEGUARD_PAYLOAD_EOF__"
TEMPLATE = "bootstrap.sh"

TEXT_SUFFIXES = {".py", ".sh", ".html", ".js", ".css", ".json", ".svg"}
SAFE_PATH_RE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_./-]*")


def package_files(package_dir: Path) -> dict[str, str]:
    """The program's files as {path relative to the package's parent: text}."""
    files = {}
    for path in sorted(package_dir.rglob("*")):
        if path.is_file() and path.suffix in TEXT_SUFFIXES and "__pycache__" not in path.parts:
            files[path.relative_to(package_dir.parent).as_posix()] = path.read_text()
    return files


def build_installer(files: dict[str, str], version: str, data: str | None = None) -> str:
    """Return the installer script for these program files.

    With `data`, the script is a backup: it also carries that text and
    restores it on the server it is run on.
    """
    template = files[f"byteguard/{TEMPLATE}"]
    for mark in (PAYLOAD_MARK, DATA_MARK):
        if template.count(mark) != 1:
            raise ValueError(f"{TEMPLATE} must contain {mark} exactly once")
    # One pass, so a marker inside an embedded file is never replaced.
    parts = {
        VERSION_MARK: version,
        PAYLOAD_MARK: _extract_function(files),
        DATA_MARK: "" if data is None else _data_function(data),
    }
    return re.sub("|".join(map(re.escape, parts)), lambda match: parts[match.group()], template)


def _data_function(data: str) -> str:
    if DATA_DELIMITER in data.splitlines():
        raise ValueError("the backup data contains the heredoc delimiter on a line of its own")
    if not data.endswith("\n"):
        data += "\n"
    return f"restore_data() {{\n  cat >\"$1\" <<'{DATA_DELIMITER}'\n{data}{DATA_DELIMITER}\n}}"


def _extract_function(files: dict[str, str]) -> str:
    lines = ["extract_payload() {", '  local dest="$1"']
    directories = sorted({str(Path(name).parent) for name in files})
    lines.append("  mkdir -p " + " ".join(f'"$dest/{directory}"' for directory in directories))
    for name, text in files.items():
        if not SAFE_PATH_RE.fullmatch(name) or ".." in name:
            raise ValueError(f"unsafe file name in the bundle: {name!r}")
        if DELIMITER in text.splitlines():
            raise ValueError(f"{name} contains the heredoc delimiter on a line of its own")
        if not text.endswith("\n"):
            text += "\n"
        lines.append(f"  cat >\"$dest/{name}\" <<'{DELIMITER}'")
        lines.append(text + DELIMITER)
    lines.append("}")
    return "\n".join(lines)
