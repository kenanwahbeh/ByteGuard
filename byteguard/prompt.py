"""Asking questions on the terminal."""

import sys

from byteguard.errors import ByteGuardError


class Terminal:
    def __init__(self, read_line, write):
        self._read_line = read_line
        self._write = write

    def say(self, text: str = "") -> None:
        self._write(text + "\n")

    def _answer(self, prompt: str) -> str:
        self._write(prompt)
        line = self._read_line()
        if line == "":
            raise ByteGuardError("The input ended before the questions were answered.")
        return line.strip()

    def ask(self, question: str, default: str | None = None) -> str:
        suffix = f" [{default}]" if default else ""
        return self._answer(f"{question}{suffix}: ") or (default or "")

    def confirm(self, question: str, default: bool = True) -> bool:
        hint = "Y/n" if default else "y/N"
        while True:
            answer = self._answer(f"{question} [{hint}]: ").lower()
            if not answer:
                return default
            if answer in ("y", "yes"):
                return True
            if answer in ("n", "no"):
                return False

    def choose(self, question: str, options: list[str]) -> int:
        """Show a numbered list and return the index of the chosen option."""
        for number, option in enumerate(options, start=1):
            self.say(f"  {number}) {option}")
        while True:
            answer = self._answer(f"{question} [1-{len(options)}]: ")
            if answer.isdigit() and 1 <= int(answer) <= len(options):
                return int(answer) - 1


def open_terminal() -> Terminal:
    """A terminal to ask on, even when the installer itself arrived on standard input."""

    def write_stdout(text: str) -> None:
        sys.stdout.write(text)
        sys.stdout.flush()

    if sys.stdin.isatty():
        return Terminal(sys.stdin.readline, write_stdout)
    try:
        tty = open("/dev/tty", "r+")
    except OSError:
        raise ByteGuardError(
            "There is no terminal to ask the setup questions on. "
            "Run it from a terminal, or pass --non-interactive."
        ) from None

    def write_tty(text: str) -> None:
        tty.write(text)
        tty.flush()

    return Terminal(tty.readline, write_tty)
