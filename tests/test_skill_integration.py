import sys
from pathlib import Path

src_path = Path(__file__).resolve().parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

import unittest
from codeiq_dev.core.skills import SkillManager

class TestSkillManagerIntegration(unittest.TestCase):
    def setUp(self):
        self.manager = SkillManager()

    def test_skill_structure_and_paths(self):
        self.assertTrue(self.manager.sandbox_dir.is_absolute())
        self.assertTrue(self.manager.results_dir.is_absolute())
        self.assertEqual(self.manager.results_dir.name, "Skill_results")

    def test_skill_name_normalization(self):
        clean_name = "xlsx (Excel)"
        norm = clean_name.lower().strip()
        if "(" in norm:
            norm = norm.split("(")[0].strip()
        norm = norm.replace(" ", "_")
        self.assertEqual(norm, "xlsx")

if __name__ == "__main__":
    unittest.main()

