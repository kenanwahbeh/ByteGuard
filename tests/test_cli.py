import contextlib
import io
import unittest

from byteguard import __version__
from byteguard.cli import main


class CliTest(unittest.TestCase):
    def test_version_flag_prints_the_version_and_exits_cleanly(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit) as raised:
            main(["--version"])

        self.assertEqual(raised.exception.code, 0)
        self.assertEqual(out.getvalue().strip(), f"byteguard {__version__}")

    def test_no_arguments_shows_the_help(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main([])

        self.assertEqual(code, 0)
        self.assertIn("usage: byteguard", out.getvalue())


if __name__ == "__main__":
    unittest.main()
