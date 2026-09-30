#!/usr/bin/env python3
"""Build dist/byteguard.sh, the single installer file."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from byteguard import __version__, bundle  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-o", "--output", type=Path, default=ROOT / "dist" / "byteguard.sh")
    args = parser.parse_args()

    installer = bundle.build_installer(bundle.package_files(ROOT / "byteguard"), __version__)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(installer)
    args.output.chmod(0o755)
    print(args.output)


if __name__ == "__main__":
    main()
