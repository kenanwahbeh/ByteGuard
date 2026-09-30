import stat
import unittest

from byteguard import state
from byteguard.errors import ByteGuardError
from fakes import temp_paths


class StateFileTest(unittest.TestCase):
    def setUp(self):
        self.path = temp_paths(self).state

    def test_a_missing_file_means_not_set_up(self):
        self.assertIsNone(state.load(self.path))

    def test_what_is_saved_is_loaded_back(self):
        data = {"schema": state.SCHEMA, "devices": [{"name": "phone"}]}
        state.save(self.path, data)

        self.assertEqual(state.load(self.path), data)

    def test_the_file_and_its_directory_are_private_to_the_owner(self):
        state.save(self.path, {"schema": state.SCHEMA})

        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.path.parent.stat().st_mode), 0o700)

    def test_saving_leaves_no_temporary_files_behind(self):
        state.save(self.path, {"schema": state.SCHEMA})
        state.save(self.path, {"schema": state.SCHEMA})

        self.assertEqual([p.name for p in self.path.parent.iterdir()], ["state.json"])

    def test_a_file_from_another_schema_is_refused(self):
        state.save(self.path, {"schema": state.SCHEMA + 1})

        with self.assertRaises(ByteGuardError):
            state.load(self.path)


if __name__ == "__main__":
    unittest.main()
