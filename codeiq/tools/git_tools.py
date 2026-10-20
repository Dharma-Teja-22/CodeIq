"""Git integration tools for CodeIq."""

from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import subprocess
from typing import List, Optional, Tuple


@dataclass
class GitStatusSummary:
    branch: str = "unknown"
    staged: List[str] = None
    modified: List[str] = None
    untracked: List[str] = None
    is_git_repo: bool = False

    def __post_init__(self):
        if self.staged is None:
            self.staged = []
        if self.modified is None:
            self.modified = []
        if self.untracked is None:
            self.untracked = []

    @property
    def badge(self) -> str:
        if not self.is_git_repo:
            return "no-git"
        parts = [f"🌱 {self.branch}"]
        changes = []
        if self.modified:
            changes.append(f"~{len(self.modified)}")
        if self.staged:
            changes.append(f"+{len(self.staged)}")
        if self.untracked:
            changes.append(f"?{len(self.untracked)}")
        if changes:
            parts.append(f"({' '.join(changes)})")
        else:
            parts.append("(clean)")
        return " ".join(parts)


def run_git(args: List[str], cwd: Optional[Path] = None) -> Tuple[int, str]:
    work_dir = str(cwd or Path.cwd())
    try:
        proc = subprocess.run(
            ["git"] + args,
            cwd=work_dir,
            capture_output=True,
            text=True,
            shell=False,
            encoding="utf-8",
            errors="replace",
        )
        output = (proc.stdout + proc.stderr).strip()
        return proc.returncode, output
    except Exception as e:
        return 1, str(e)


def get_git_status_summary(cwd: Optional[Path] = None) -> GitStatusSummary:
    code, branch_out = run_git(["branch", "--show-current"], cwd)
    if code != 0:
        return GitStatusSummary(is_git_repo=False)

    branch = branch_out.strip() or "HEAD (detached)"
    summary = GitStatusSummary(branch=branch, is_git_repo=True)

    code, status_out = run_git(["status", "--porcelain"], cwd)
    if code == 0 and status_out:
        for line in status_out.splitlines():
            if len(line) < 3:
                continue
            index_status = line[0]
            worktree_status = line[1]
            fname = line[3:].strip()

            if index_status in ("M", "A", "R", "D"):
                summary.staged.append(fname)
            if worktree_status in ("M", "D"):
                summary.modified.append(fname)
            elif index_status == "?" and worktree_status == "?":
                summary.untracked.append(fname)

    return summary


def git_status(cwd: Optional[Path] = None) -> str:
    """Returns human-readable git status summary."""
    summary = get_git_status_summary(cwd)
    if not summary.is_git_repo:
        return "Current directory is not a Git repository."

    lines = [f"Branch: {summary.branch}"]
    if summary.staged:
        lines.append(f"Staged changes ({len(summary.staged)}):")
        for f in summary.staged:
            lines.append(f"  + {f}")
    if summary.modified:
        lines.append(f"Unstaged modifications ({len(summary.modified)}):")
        for f in summary.modified:
            lines.append(f"  ~ {f}")
    if summary.untracked:
        lines.append(f"Untracked files ({len(summary.untracked)}):")
        for f in summary.untracked:
            lines.append(f"  ? {f}")
    if not summary.staged and not summary.modified and not summary.untracked:
        lines.append("Working tree clean. No pending changes.")

    return "\n".join(lines)


def git_diff(file_path: Optional[str] = None, staged: bool = False, cwd: Optional[Path] = None) -> str:
    """Shows git unified diff."""
    args = ["diff"]
    if staged:
        args.append("--staged")
    if file_path:
        args.extend(["--", file_path])

    code, output = run_git(args, cwd)
    if code != 0:
        return f"Error executing git diff: {output}"
    return output if output else "No changes detected in git diff."


def git_log(max_count: int = 5, cwd: Optional[Path] = None) -> str:
    """Shows recent commit history."""
    args = ["log", f"-n{max_count}", "--pretty=format:%h - %an, %ar : %s"]
    code, output = run_git(args, cwd)
    if code != 0:
        return f"Error executing git log: {output}"
    return output if output else "No commits found."


def git_commit(message: str, cwd: Optional[Path] = None) -> str:
    """Commits all tracked modified files with a message."""
    code, add_out = run_git(["add", "-u"], cwd)
    if code != 0:
        return f"Error staging changes: {add_out}"

    code, commit_out = run_git(["commit", "-m", message], cwd)
    if code != 0:
        return f"Error committing: {commit_out}"
    return f"Commit successful:\n{commit_out}"
