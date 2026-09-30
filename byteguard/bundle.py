"""Building the single installer file: the bootstrap script with the program embedded in it.

The program files go in as plain text between heredoc markers, not as a
compressed blob, so the installer can be read from top to bottom before it
is run.
"""

import re
from pathlib import Path

PAYLOAD_MARK = "# @@BYTEGUARD_PAYLOAD@@"
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


def build_installer(files: dict[str, str], version: str) -> str:
    """Return the installer script for these program files."""
    template = files[f"byteguard/{TEMPLATE}"]
    if template.count(PAYLOAD_MARK) != 1:
        raise ValueError(f"{TEMPLATE} must contain the payload marker exactly once")
    return template.replace(VERSION_MARK, version).replace(PAYLOAD_MARK, _extract_function(files))


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
