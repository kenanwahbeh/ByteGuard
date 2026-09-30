"""The `byteguard` command."""

import argparse

from byteguard import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="byteguard",
        description="Install and manage a WireGuard server.",
    )
    parser.add_argument(
        "--version", action="version", version=f"byteguard {__version__}"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    parser.parse_args(argv)
    parser.print_help()
    return 0
