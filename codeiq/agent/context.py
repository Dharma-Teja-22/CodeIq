"""Context manager for workspace indexing and @file mention resolution."""

from __future__ import annotations
import os
from pathlib import Path
import re
from typing import List, Optional, Tuple

from ..tools.file_tools import get_ignored_patterns, is_ignored, read_file


class ContextManager:
    """Provides project-level context, summaries, and @file mention expansions."""

    def __init__(self, cwd: Path):
        self.cwd = cwd.resolve()

    def generate_project_overview(self, max_files: int = 40) -> str:
        """Produces a concise tree representation of the workspace for system prompts."""
        patterns = get_ignored_patterns(self.cwd)
        lines = [f"{self.cwd.name}/"]
        count = 0

        for root, dirs, files in os.walk(self.cwd):
            try:
                rel_root = Path(root).relative_to(self.cwd).as_posix()
            except ValueError:
                continue

            if rel_root != ".":
                if is_ignored(rel_root, patterns):
                    dirs[:] = []
                    continue

            # Filter dirs
            dirs[:] = [
                d for d in dirs
                if not is_ignored(f"{rel_root}/{d}".lstrip("./"), patterns)
            ]

            depth = rel_root.count("/") if rel_root != "." else 0
            if depth > 2:
                continue

            indent = "  " * (depth + 1)
            for f in sorted(files):
                rel_file = f"{rel_root}/{f}".lstrip("./")
                if not is_ignored(rel_file, patterns):
                    lines.append(f"{indent}{f}")
                    count += 1
                    if count >= max_files:
                        lines.append(f"{indent}... [and more files]")
                        return "\n".join(lines)

        return "\n".join(lines)

    def extract_file_mentions(self, text: str) -> List[str]:
        """Finds all @path or @filename tokens in a user prompt."""
        # Matches patterns like @main.py, @src/app.py, @"path with spaces"
        matches = re.findall(r'@(?:\"([^\"]+)\"|([a-zA-Z0-9_\-\.\/\\+]+))', text)
        files = []
        for quoted, unquoted in matches:
            mention = quoted or unquoted
            if mention and not mention.startswith("@"):
                files.append(mention)
        return files

    def resolve_mentions_and_enrich_prompt(self, user_prompt: str) -> Tuple[str, List[str]]:
        """Extracts @file mentions, loads file contents, and appends them to prompt context."""
        mentions = self.extract_file_mentions(user_prompt)
        if not mentions:
            return user_prompt, []

        resolved_files = []
        context_blocks = []

        for mention in mentions:
            target = (self.cwd / mention).resolve()
            if not target.exists():
                # Search case-insensitively or as relative filename
                for candidate in self.cwd.glob(f"**/{mention}"):
                    if candidate.is_file():
                        target = candidate
                        break

            if target.exists() and target.is_file():
                try:
                    rel_name = target.relative_to(self.cwd).as_posix()
                except ValueError:
                    rel_name = target.name

                content = read_file(str(target), start_line=1, end_line=300, cwd=self.cwd)
                context_blocks.append(f"\n### Attached File Context: `{rel_name}`\n{content}\n")
                resolved_files.append(rel_name)

        if context_blocks:
            enriched = user_prompt + "\n\n" + "\n".join(context_blocks)
            return enriched, resolved_files

        return user_prompt, []
