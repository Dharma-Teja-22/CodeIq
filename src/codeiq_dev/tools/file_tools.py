from pathlib import Path
from typing import List, Union

IGNORE_DIRS = {"node_modules", ".git", "venv", ".env", ".venv", "env", "__pycache__","dist", "build", ".pytest_cache", ".mypy_cache", ".ruff_cache",".turbo", ".next", ".nuxt", ".cache", ".idea", ".vscode", ".vs",".coverage", "htmlcov"}
IGNORE_EXTS = {".pyc", ".pyo", ".pyd"}

def findFile(target_directory: Union[str, Path] = ".", filename: str = "") -> List[Path]:
    """
    Search recursively for a file by name (matching filename with or without extension)
    in the target directory, skipping common ignored directories.
    """
    search_dir = Path(target_directory).resolve()
    if not search_dir.exists():
        return []

    target_name = Path(filename).name.lower()
    target_stem = Path(filename).stem.lower()

    matches: List[Path] = []
    for path in search_dir.rglob("*"):
        if path.is_dir():
            continue
        if any(ignore_dir in path.parts for ignore_dir in IGNORE_DIRS):
            continue
        if path.suffix.lower() in IGNORE_EXTS:
            continue
        
        # Match full filename (e.g. cli.py) or stem (e.g. cli)
        if path.name.lower() == target_name or path.stem.lower() == target_stem:
            matches.append(path)
    return matches

PROTECTED_FILES = {".env", ".env.local", ".env.production", ".env.development", ".env.test"}

def is_protected_file(path_or_name: Union[str, Path]) -> bool:
    """Check if the target filename is a protected sensitive file (e.g. .env)."""
    p = Path(path_or_name)
    name = p.name.lower()
    return name in PROTECTED_FILES or name.startswith(".env.") or name.endswith(".env")

def resolveFilePath(file_path: Union[str, Path], target_directory: Union[str, Path] = ".") -> Union[Path, str, List[Path]]:
    """
    Resolves a file path:
    1. Checks if file_path exists directly (relative or absolute).
    2. Searches with findFile.
    3. If multiple matches exist, returns the list so the caller/user can select.
    """
    if is_protected_file(file_path):
        return "Access denied: Reading or modifying .env and sensitive environment files is strictly restricted."

    p = Path(file_path)
    if p.is_file():
        return p.resolve()

    matches = findFile(target_directory=target_directory, filename=str(file_path))
    if not matches:
        return f"File '{file_path}' not found."
    if len(matches) == 1:
        return matches[0]
    return matches  # Multiple matches found

def readFile(filename: str, target_directory: Union[str, Path] = ".") -> str:
    """Find a file and read its content."""
    if is_protected_file(filename):
        return "Access denied: Reading .env and sensitive environment files is strictly prohibited for security reasons."

    resolved = resolveFilePath(filename, target_directory=target_directory)
    if isinstance(resolved, str):
        return resolved
    if isinstance(resolved, list):
        return f"Multiple files found for '{filename}':\n" + "\n".join(f" - {f}" for f in resolved)

    try:
        with open(resolved, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Error reading file '{resolved}': {e}"

def writeFile(filename: str, content: str, mode: str = "w", target_directory: Union[str, Path] = ".") -> str:
    """
    Write content to a file (default 'w' to overwrite/create, avoiding duplicates).
    """
    resolved = resolveFilePath(filename, target_directory=target_directory)
    if isinstance(resolved, list):
        resolved = resolved[0]
    elif isinstance(resolved, str) and "not found" in resolved:
        resolved = (Path(target_directory).resolve() / filename).resolve()

    try:
        resolved.parent.mkdir(parents=True, exist_ok=True)
        with open(resolved, mode, encoding="utf-8") as f:
            f.write(content)
        return f"Successfully wrote to '{resolved}'."
    except Exception as e:
        return f"Error writing to file '{resolved}': {e}"

def replaceInFile(file_path: Union[str, Path], old_code: str, new_code: str, target_directory: Union[str, Path] = ".") -> str:
    """
    Finds the file and replaces an existing code block with new code.
    Returns only the snippet of change rather than full file.
    """
    resolved = resolveFilePath(file_path, target_directory=target_directory)
    if isinstance(resolved, str):
        return resolved
    if isinstance(resolved, list):
        return f"Multiple files found for '{file_path}':\n" + "\n".join(f" - {f}" for f in resolved)

    try:
        with open(resolved, "r", encoding="utf-8") as f:
            content = f.read()

        if old_code not in content:
            return f"Error: Target code block not found in '{resolved.name}'. Check indentation and lines."

        if content.count(old_code) > 1:
            return f"Error: Target code block appears {content.count(old_code)} times in '{resolved.name}'. Include more context."

        new_content = content.replace(old_code, new_code, 1)

        with open(resolved, "w", encoding="utf-8") as f:
            f.write(new_content)

        # Return snippet preview rather than entire file
        old_preview = "\n".join(f"- {line}" for line in old_code.strip().splitlines()[:5])
        new_preview = "\n".join(f"+ {line}" for line in new_code.strip().splitlines()[:5])
        return f"Successfully updated '{resolved.name}':\n{old_preview}\n{new_preview}"
    except Exception as e:
        return f"Error updating '{resolved}': {e}"

def fileOperation(
    operation: str,
    filename: str = "",
    file_path: Union[str, Path] = "",
    content: str = "",
    old_code: str = "",
    new_code: str = "",
    target_directory: Union[str, Path] = "."
):
    """Dispatch file operations."""
    path_to_use = file_path or filename

    if operation == "find_file":
        matches = findFile(target_directory=target_directory, filename=str(path_to_use))
        return [str(p) for p in matches]
    elif operation == "read_file":
        return readFile(filename=str(path_to_use), target_directory=target_directory)
    elif operation == "write_file":
        return writeFile(filename=str(path_to_use), content=content, target_directory=target_directory)
    elif operation == "replace_content":
        return replaceInFile(file_path=path_to_use, old_code=old_code, new_code=new_code, target_directory=target_directory)
    return f"Unsupported file operation: {operation}"



