"""File exploration, reading, writing, and editing tools."""

from __future__ import annotations
import fnmatch
import os
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple


def get_ignored_patterns(base_path: Path) -> List[str]:
    """Load ignore patterns from .gitignore, .codeiqignore, and standard defaults."""
    patterns = [
        ".git",
        ".git/*",
        ".codeiq",
        ".codeiq/*",
        "__pycache__",
        "*.pyc",
        "node_modules",
        "node_modules/*",
        ".venv",
        "venv",
        "env",
        ".env",
        ".pytest_cache",
        ".mypy_cache",
        "dist",
        "build",
        "*.egg-info",
        ".DS_Store",
    ]
    for ignore_file in (".codeiqignore", ".gitignore"):
        p = base_path / ignore_file
        if p.exists() and p.is_file():
            try:
                for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
                    line = line.strip()
                    if line and not line.startswith("#"):
                        patterns.append(line)
            except Exception:
                pass
    return patterns


def is_ignored(rel_path: str, patterns: List[str]) -> bool:
    rel_norm = rel_path.replace("\\", "/")
    parts = rel_norm.split("/")
    for pat in patterns:
        pat_clean = pat.rstrip("/")
        for part in parts:
            if fnmatch.fnmatch(part, pat_clean):
                return True
        if fnmatch.fnmatch(rel_norm, pat) or fnmatch.fnmatch(rel_norm, f"*/{pat}"):
            return True
    return False


def resolve_path(path_str: str, base_dir: Path) -> Path:
    p = Path(path_str)
    if not p.is_absolute():
        p = (base_dir / p).resolve()
    return p


def read_file(path: str, start_line: Optional[int] = None, end_line: Optional[int] = None, cwd: Optional[Path] = None) -> str:
    """Reads file content with line numbers, optionally within a specified range."""
    base_dir = cwd or Path.cwd()
    target = resolve_path(path, base_dir)

    if not target.exists():
        return f"Error: File '{path}' does not exist at {target}."
    if not target.is_file():
        return f"Error: '{path}' is a directory, not a file."

    try:
        content = target.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"Error reading file '{path}': {e}"

    lines = content.splitlines()
    total_lines = len(lines)

    start = max(1, start_line) if start_line is not None else 1
    end = min(total_lines, end_line) if end_line is not None else total_lines

    if start > total_lines:
        return f"File '{path}' has {total_lines} lines. Requested start line {start} is out of bounds."

    output_lines = []
    output_lines.append(f"--- File: {target.name} ({start}-{end} of {total_lines} lines) ---")
    for idx in range(start - 1, end):
        line_num = idx + 1
        output_lines.append(f"{line_num:5d} | {lines[idx]}")

    return "\n".join(output_lines)


def write_file(path: str, content: str, cwd: Optional[Path] = None) -> str:
    """Creates a new file or completely replaces an existing file with the provided content."""
    base_dir = cwd or Path.cwd()
    target = resolve_path(path, base_dir)

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"Successfully wrote {len(content.splitlines())} lines to '{path}'."
    except Exception as e:
        return f"Error writing to '{path}': {e}"


def edit_file(path: str, old_str: str, new_str: str, cwd: Optional[Path] = None) -> str:
    """Replaces a targeted occurrence of old_str with new_str in a file."""
    base_dir = cwd or Path.cwd()
    target = resolve_path(path, base_dir)

    if not target.exists() or not target.is_file():
        return f"Error: File '{path}' does not exist."

    try:
        current_text = target.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"Error reading '{path}': {e}"

    occurrences = current_text.count(old_str)
    if occurrences == 0:
        return (
            f"Error: Target text to replace was not found in '{path}'. "
            f"Please verify exact whitespace, indentation, and line breaks."
        )

    if occurrences > 1:
        return (
            f"Error: Target text occurs {occurrences} times in '{path}'. "
            f"Please provide more surrounding context lines so the target is unique."
        )

    updated_text = current_text.replace(old_str, new_str, 1)
    try:
        target.write_text(updated_text, encoding="utf-8")
        return f"Successfully updated '{path}'."
    except Exception as e:
        return f"Error saving updated '{path}': {e}"


def list_dir(path: str = ".", recursive: bool = False, depth: int = 2, cwd: Optional[Path] = None) -> str:
    """Lists files and directories in a path, respecting ignored patterns."""
    base_dir = cwd or Path.cwd()
    target = resolve_path(path, base_dir)

    if not target.exists() or not target.is_dir():
        return f"Error: Directory '{path}' does not exist or is not a folder."

    patterns = get_ignored_patterns(base_dir)
    results = []

    def _walk(cur_dir: Path, current_depth: int, prefix: str = ""):
        try:
            entries = sorted(cur_dir.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
        except PermissionError:
            results.append(f"{prefix}[Permission Denied]")
            return

        for idx, entry in enumerate(entries):
            try:
                rel = entry.relative_to(base_dir).as_posix()
            except ValueError:
                rel = entry.name

            if is_ignored(rel, patterns):
                continue

            is_last = idx == len(entries) - 1
            connector = "└── " if is_last else "├── "
            child_prefix = prefix + ("    " if is_last else "│   ")

            if entry.is_dir():
                results.append(f"{prefix}{connector}{entry.name}/")
                if recursive and current_depth < depth:
                    _walk(entry, current_depth + 1, child_prefix)
            else:
                size_str = f"{entry.stat().st_size:,} B" if entry.exists() else "?"
                results.append(f"{prefix}{connector}{entry.name} ({size_str})")

    results.append(f"📁 {target.name or '.'}/")
    _walk(target, 1)
    return "\n".join(results)


def search_files(pattern: str, path: str = ".", cwd: Optional[Path] = None) -> str:
    """Finds files matching a glob pattern."""
    base_dir = cwd or Path.cwd()
    target = resolve_path(path, base_dir)

    if not target.exists() or not target.is_dir():
        return f"Error: Directory '{path}' does not exist."

    patterns = get_ignored_patterns(base_dir)
    matches = []

    for root, dirs, files in os.walk(target):
        # Filter out ignored dirs in-place to prune walk
        rel_root = Path(root).relative_to(base_dir).as_posix()
        dirs[:] = [d for d in dirs if not is_ignored(f"{rel_root}/{d}".lstrip("./"), patterns)]

        for f in files:
            rel_file = Path(root, f).relative_to(base_dir).as_posix()
            if is_ignored(rel_file, patterns):
                continue
            if fnmatch.fnmatch(f, pattern) or fnmatch.fnmatch(rel_file, pattern):
                matches.append(rel_file)

    if not matches:
        return f"No files matched pattern '{pattern}'."
    return f"Found {len(matches)} matching file(s):\n" + "\n".join(f"- {m}" for m in matches[:100])


def grep_search(query: str, path: str = ".", is_regex: bool = False, cwd: Optional[Path] = None) -> str:
    """Searches for text content inside files across the workspace."""
    base_dir = cwd or Path.cwd()
    target = resolve_path(path, base_dir)

    if not target.exists():
        return f"Error: Path '{path}' does not exist."

    patterns = get_ignored_patterns(base_dir)
    flags = re.IGNORECASE
    try:
        matcher = re.compile(query if is_regex else re.escape(query), flags)
    except re.error as e:
        return f"Invalid regex query: {e}"

    results = []
    total_matches = 0

    files_to_check = []
    if target.is_file():
        files_to_check.append(target)
    else:
        for root, dirs, files in os.walk(target):
            rel_root = Path(root).relative_to(base_dir).as_posix()
            dirs[:] = [d for d in dirs if not is_ignored(f"{rel_root}/{d}".lstrip("./"), patterns)]
            for f in files:
                rel_file = Path(root, f).relative_to(base_dir).as_posix()
                if not is_ignored(rel_file, patterns):
                    files_to_check.append(Path(root, f))

    for fpath in files_to_check:
        try:
            rel_name = fpath.relative_to(base_dir).as_posix()
            content = fpath.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        file_matches = []
        for line_idx, line in enumerate(content.splitlines()):
            if matcher.search(line):
                file_matches.append(f"  {line_idx + 1:4d}: {line.strip()[:140]}")
                total_matches += 1
                if total_matches >= 80:
                    break

        if file_matches:
            results.append(f"📄 {rel_name}:")
            results.extend(file_matches)

        if total_matches >= 80:
            results.append("... [Search truncated at 80 matches]")
            break

    if not results:
        return f"No matches found for query: '{query}'."
    return "\n".join(results)
