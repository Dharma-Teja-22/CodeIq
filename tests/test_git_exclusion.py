import sys
from pathlib import Path

src_path = Path(__file__).resolve().parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

import unittest
from unittest.mock import patch, MagicMock
from neo.tools.git_tools import gitAdd, gitCommit, gitOperation

class TestGitExclusion(unittest.TestCase):
    @patch("neo.tools.git_tools.subprocess.run")
    def test_git_add_with_single_exclude(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stderr="", stdout="")

        res = gitAdd(file_name=".", exclude="secret.env")
        self.assertIn("Successfully staged changes excluding: secret.env", res)

        # Verify git add -A was called, followed by git reset HEAD -- secret.env
        calls = mock_run.call_args_list
        self.assertEqual(calls[0][0][0], ["git", "add", "-A"])
        self.assertEqual(calls[1][0][0], ["git", "reset", "HEAD", "--", "secret.env"])

    @patch("neo.tools.git_tools.subprocess.run")
    def test_git_add_with_multiple_excludes(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stderr="", stdout="")

        res = gitAdd(file_name=".", exclude="test.py, ignore.txt")
        self.assertIn("Successfully staged changes excluding: test.py, ignore.txt", res)

        calls = mock_run.call_args_list
        self.assertEqual(calls[0][0][0], ["git", "add", "-A"])
        self.assertEqual(calls[1][0][0], ["git", "reset", "HEAD", "--", "test.py"])
        self.assertEqual(calls[2][0][0], ["git", "reset", "HEAD", "--", "ignore.txt"])

    @patch("neo.tools.git_tools.subprocess.run")
    def test_git_add_specific_files_with_exclude(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stderr="", stdout="")

        res = gitAdd(file_name="app.py, secret.env", exclude="secret.env")
        self.assertIn("Successfully staged changes: app.py", res)

        mock_run.assert_called_once_with(["git", "add", "--", "app.py"], capture_output=True, text=True)

    @patch("neo.tools.git_tools.subprocess.run")
    def test_git_add_all_targets_excluded(self, mock_run):
        res = gitAdd(file_name="secret.env", exclude="secret.env")
        self.assertIn("No files staged. All specified targets were excluded", res)

    @patch("neo.tools.git_tools.subprocess.run")
    def test_git_commit_with_exclude(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stderr="", stdout="")

        res = gitCommit(message="feat: new feature", exclude="temp.log")
        self.assertIn("Commit successful: feat: new feature", res)

        calls = mock_run.call_args_list
        self.assertEqual(calls[0][0][0], ["git", "reset", "HEAD", "--", "temp.log"])
        self.assertEqual(calls[1][0][0], ["git", "commit", "-m", "feat: new feature"])

    @patch("neo.tools.git_tools.subprocess.run")
    def test_git_operation_dispatches_exclude(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stderr="", stdout="")

        res = gitOperation(operation="add", file_name=".", exclude="excluded.py")
        self.assertIn("Successfully staged changes excluding: excluded.py", res)

        calls = mock_run.call_args_list
        self.assertEqual(calls[0][0][0], ["git", "add", "-A"])
        self.assertEqual(calls[1][0][0], ["git", "reset", "HEAD", "--", "excluded.py"])

if __name__ == "__main__":
    unittest.main()

