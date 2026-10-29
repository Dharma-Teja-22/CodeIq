from pathlib import Path
from typing import List, Union

IGNORE_DIRS = {"node_modules", ".git", "venv", ".env", ".venv", "env", "__pycache__","dist", "build", ".pytest_cache", ".mypy_cache", ".ruff_cache",".turbo", ".next", ".nuxt", ".cache", ".idea", ".vscode", ".vs",".coverage", "htmlcov"}
IGNORE_EXTS = {".pyc", ".pyo", ".pyd"}

def findFile(target_directory: Union[str, Path] = ".", filename: str = "") -> List[Path]:
    """
    Search recursively for a file by name (matching any extension) in the target directory,
    skipping common ignored directories and binary extensions.
    """
    search_dir = Path(target_directory).resolve()
    if not search_dir.exists():
        return []

    matches: List[Path] = []
    for path in search_dir.rglob("*"):
        # Skip if it's a directory
        if path.is_dir():
            continue
        # Skip if it's in an ignored directory
        if any(ignore_dir in path.parts for ignore_dir in IGNORE_DIRS):
            continue
        # Skip if it has an ignored extension
        if path.suffix.lower() in IGNORE_EXTS:
            continue
        # Check if the filename (without extension) matches
        if path.stem == filename:
            matches.append(path)
    return matches

def readFile(filename: str, target_directory: Union[str, Path] = ".") -> str:
    """
    Find a file by name using findFile and read its content.
    If multiple matches are found, it reads the first match.
    """
    matches = findFile(target_directory=target_directory, filename=filename)
    if not matches:
        return f"File '{filename}' not found."

    file_path = matches[0]
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Error reading file '{file_path}': {e}"

def fileOperation(operation: str, filename: str = "", target_directory: Union[str, Path] = "."):
    """Dispatch file operations."""
    if operation == "find_file":
        return findFile(target_directory=target_directory, filename=filename)
    elif operation == "read_file":
        return readFile(filename=filename, target_directory=target_directory)
    return f"Unsupported file operation: {operation}"

