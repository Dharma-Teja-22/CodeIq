"""Diff computation and formatting engine for CodeIq."""

from __future__ import annotations
from dataclasses import dataclass
import difflib
from pathlib import Path
from typing import Optional


@dataclass
class DiffResult:
    filename: str
    diff_text: str
    additions: int
    deletions: int
    is_new_file: bool = False
    is_deletion: bool = False

    @property
    def summary(self) -> str:
        return f"{self.filename} (+{self.additions} / -{self.deletions})"


class DiffEngine:
    """Computes unified diffs and formats them with Rich styling."""

    @staticmethod
    def compute_diff(
        filename: str,
        old_text: str,
        new_text: str,
        from_label: str = "before",
        to_label: str = "after",
    ) -> DiffResult:
        old_lines = old_text.splitlines(keepends=True)
        new_lines = new_text.splitlines(keepends=True)

        is_new = len(old_text.strip()) == 0 and len(new_text.strip()) > 0
        is_del = len(old_text.strip()) > 0 and len(new_text.strip()) == 0

        diff_gen = difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"a/{filename} ({from_label})",
            tofile=f"b/{filename} ({to_label})",
            lineterm="",
        )
        diff_lines = list(diff_gen)
        diff_text = "\n".join(line.rstrip("\r\n") for line in diff_lines)

        additions = 0
        deletions = 0
        for line in diff_lines:
            if line.startswith("+") and not line.startswith("+++"):
                additions += 1
            elif line.startswith("-") and not line.startswith("---"):
                deletions += 1

        return DiffResult(
            filename=filename,
            diff_text=diff_text if diff_text else "(No changes detected)",
            additions=additions,
            deletions=deletions,
            is_new_file=is_new,
            is_deletion=is_del,
        )

    @classmethod
    def preview_write(cls, file_path: Path, new_content: str) -> DiffResult:
        rel_name = str(file_path)
        old_content = ""
        if file_path.exists() and file_path.is_file():
            try:
                old_content = file_path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                old_content = ""
        return cls.compute_diff(rel_name, old_content, new_content)

    @classmethod
    def preview_edit(cls, file_path: Path, old_str: str, new_str: str) -> Optional[DiffResult]:
        if not file_path.exists() or not file_path.is_file():
            return None
        try:
            current_content = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return None

        if old_str not in current_content:
            return None

        updated_content = current_content.replace(old_str, new_str, 1)
        return cls.compute_diff(str(file_path), current_content, updated_content)
