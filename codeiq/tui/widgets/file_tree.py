"""Interactive project directory explorer widget."""

from __future__ import annotations
from pathlib import Path
from typing import Iterable
from textual.message import Message
from textual.widgets import DirectoryTree

from ...tools.file_tools import get_ignored_patterns, is_ignored


class WorkspaceFileTree(DirectoryTree):
    """File explorer tree that filters out ignored files and emits file events."""

    class FilePicked(Message):
        """Emitted when user selects a file in the tree."""
        def __init__(self, path: Path):
            self.path = path
            super().__init__()

    def __init__(self, path: Path, **kwargs):
        super().__init__(path, id="file-tree-view", **kwargs)
        self.ignored_patterns = get_ignored_patterns(path)

    def filter_paths(self, paths: Iterable[Path]) -> Iterable[Path]:
        """Filters paths according to .gitignore, .codeiqignore, and defaults."""
        filtered = []
        for p in paths:
            try:
                rel = p.relative_to(self.path).as_posix()
            except ValueError:
                rel = p.name

            if not is_ignored(rel, self.ignored_patterns):
                filtered.append(p)
        return filtered

    def on_directory_tree_file_selected(self, event: DirectoryTree.FileSelected) -> None:
        self.post_message(self.FilePicked(event.path))
