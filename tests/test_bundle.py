import subprocess
import tempfile
import unittest
from pathlib import Path

from byteguard import bundle

PACKAGE = Path(__file__).resolve().parent.parent / "byteguard"


class PackageFilesTest(unittest.TestCase):
    def test_the_program_and_the_bootstrap_template_are_collected(self):
        files = bundle.package_files(PACKAGE)

        self.assertIn("byteguard/cli.py", files)
        self.assertIn("byteguard/bootstrap.sh", files)
        self.assertFalse([name for name in files if "__pycache__" in name])


class BuildTest(unittest.TestCase):
    def setUp(self):
        self.files = bundle.package_files(PACKAGE)
        self.installer = bundle.build_installer(self.files, "9.9.9")
        self.work = Path(tempfile.mkdtemp())
        self.addCleanup(__import__("shutil").rmtree, self.work, ignore_errors=True)

    def test_the_version_is_stamped_into_the_installer(self):
        self.assertIn('BYTEGUARD_VERSION="9.9.9"', self.installer)

    def test_the_installer_is_valid_bash(self):
        script = self.work / "byteguard.sh"
        script.write_text(self.installer)

        result = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_extracting_reproduces_every_program_file_exactly(self):
        # Swap the final call to main for a call to the extraction alone, so
        # the test needs neither root nor a supported system.
        body, _, last = self.installer.rstrip("\n").rpartition("\n")
        self.assertEqual(last, 'main "$@"')
        script = self.work / "extract.sh"
        script.write_text(body + '\nextract_payload "$1"\n')
        dest = self.work / "out"
        dest.mkdir()

        subprocess.run(["bash", str(script), str(dest)], check=True)

        extracted = {p.relative_to(dest).as_posix(): p.read_text() for p in dest.rglob("*") if p.is_file()}
        self.assertEqual(extracted, self.files)

    def test_program_files_are_embedded_as_readable_text(self):
        self.assertIn("def build_installer(", self.installer)

    def test_a_file_that_would_end_its_own_heredoc_is_refused(self):
        self.files["byteguard/evil.py"] = f"x = 1\n{bundle.DELIMITER}\nrm -rf /\n"

        with self.assertRaises(ValueError):
            bundle.build_installer(self.files, "9.9.9")

    def test_a_file_name_that_could_escape_the_install_directory_is_refused(self):
        for name in ("../evil.py", "byteguard/$(id).py", "/etc/passwd"):
            files = {**self.files, name: "x = 1\n"}
            with self.subTest(name=name), self.assertRaises(ValueError):
                bundle.build_installer(files, "9.9.9")


if __name__ == "__main__":
    unittest.main()
