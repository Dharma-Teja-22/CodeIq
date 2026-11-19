import sys
from pathlib import Path

src_path = Path(__file__).resolve().parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

import unittest
from neo.core.skills import SkillManager

class TestSkillManager(unittest.TestCase):
    def setUp(self):
        self.skill_manager = SkillManager()

    def test_results_directory_exists(self):
        self.assertTrue(self.skill_manager.results_dir.exists())

    def test_sandbox_directory_exists(self):
        self.assertTrue(self.skill_manager.sandbox_dir.exists())

    def test_resolve_invalid_skill(self):
        with self.assertRaises(FileNotFoundError):
            self.skill_manager.resolve_skill_path("non_existent_skill_123456")

if __name__ == "__main__":
    unittest.main()

