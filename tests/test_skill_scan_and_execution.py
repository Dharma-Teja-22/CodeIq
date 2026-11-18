import sys
from pathlib import Path
import tempfile
import unittest

src_path = Path(__file__).resolve().parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from codeiq_dev.utils.skillMap import SkillMap
from codeiq_dev.core.skills import SkillManager


class TestSkillMapAndManager(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.skills_dir = Path(self.temp_dir.name) / "skills"
        self.skills_dir.mkdir(parents=True, exist_ok=True)

        # Create mock skills
        # 1. docx skill
        docx_dir = self.skills_dir / "docx"
        docx_dir.mkdir(parents=True, exist_ok=True)
        (docx_dir / "SKILL.md").write_text(
            "---\nname: docx\ndescription: Use this skill for Word docx manipulation.\n---\n# Docx Guide",
            encoding="utf-8"
        )

        # 2. pdf skill
        pdf_dir = self.skills_dir / "pdf"
        pdf_dir.mkdir(parents=True, exist_ok=True)
        (pdf_dir / "SKILL.md").write_text(
            "---\nname: pdf\ndescription: Use this skill for PDF processing.\n---\n# PDF Guide",
            encoding="utf-8"
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_scan_skills(self):
        sm = SkillMap(skills_dir=self.skills_dir)
        skills = sm.scan_skills()
        self.assertEqual(len(skills), 2)
        self.assertEqual(skills[0]["name"], "docx")
        self.assertEqual(skills[0]["description"], "Use this skill for Word docx manipulation.")
        self.assertEqual(skills[1]["name"], "pdf")
        self.assertEqual(skills[1]["description"], "Use this skill for PDF processing.")

    def test_skills_prompt_format(self):
        sm = SkillMap(skills_dir=self.skills_dir)
        prompt = sm.get_skills_prompt()
        self.assertIn("Available Skills:", prompt)
        self.assertIn("1. Skill Name: docx", prompt)
        self.assertIn("Path:", prompt)
        self.assertIn("Description: Use this skill for Word docx manipulation.", prompt)
        self.assertIn("2. Skill Name: pdf", prompt)

    def test_skill_manager_custom_dirs(self):
        sandbox = Path(self.temp_dir.name) / "sandbox"
        project_root = Path(self.temp_dir.name) / "project"
        manager = SkillManager(
            project_root=project_root,
            skills_dir=self.skills_dir,
            sandbox_dir=sandbox
        )
        resolved = manager.resolve_skill_path("docx")
        self.assertTrue(resolved.exists())
        self.assertEqual(resolved.parent.name, "docx")

        # Test execution
        results = manager.execute_skill("docx")
        self.assertTrue(results.exists())
        summary_file = results / "docx_execution_result.md"
        self.assertTrue(summary_file.exists())
        self.assertIn("Skill Execution Report: docx", summary_file.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

