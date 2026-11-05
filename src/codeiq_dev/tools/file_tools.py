from pathlib import Path
from typing import List, Union

IGNORE_DIRS = {"node_modules", ".git", "venv", ".env", ".venv", "env", "__pycache__","dist", "build", ".pytest_cache", ".mypy_cache", ".ruff_cache",".turbo", ".next", ".nuxt", ".cache", ".idea", ".vscode", ".vs",".coverage", "htmlcov"}
IGNORE_EXTS = {".pyc", ".pyo", ".pyd"}

def findFile(target_directory: Union[str, Path] = ".", filename: str = "") -> List[Path]:
    """
    Search recursively for a file by name in the target directory, skipping common ignored directories.

    Args:
        target_directory (Union[str, Path]): Root directory to search within. Defaults to ".".
        filename (str): Target filename or stem to search for. Defaults to "".

    Returns:
        List[Path]: List of matched Path objects found.
    """
    try:
        search_dir = Path(target_directory).resolve()
        if not search_dir.exists():
            return []

        target_name = Path(filename).name.lower()
        target_stem = Path(filename).stem.lower()

        matches: List[Path] = []
        for path in search_dir.rglob("*"):
            try:
                if path.is_dir():
                    continue
                if any(ignore_dir in path.parts for ignore_dir in IGNORE_DIRS):
                    continue
                if path.suffix.lower() in IGNORE_EXTS:
                    continue
                
                # Match full filename (e.g. cli.py) or stem (e.g. cli)
                if path.name.lower() == target_name or path.stem.lower() == target_stem:
                    matches.append(path)
            except Exception:
                continue
        return matches
    except Exception:
        return []

PROTECTED_FILES = {".env", ".env.local", ".env.production", ".env.development", ".env.test"}

def is_protected_file(path_or_name: Union[str, Path]) -> bool:
    """
    Check if the target filename is a protected sensitive file (e.g. .env).

    Args:
        path_or_name (Union[str, Path]): File path or filename to evaluate.

    Returns:
        bool: True if the file is protected/sensitive, False otherwise.
    """
    try:
        p = Path(path_or_name)
        name = p.name.lower()
        return name in PROTECTED_FILES or name.startswith(".env.") or name.endswith(".env")
    except Exception:
        return False

def resolveFilePath(file_path: Union[str, Path], target_directory: Union[str, Path] = ".") -> Union[Path, str, List[Path]]:
    """
    Resolve a file path by verifying direct existence or searching recursively.

    Args:
        file_path (Union[str, Path]): Direct path or name of the file to resolve.
        target_directory (Union[str, Path]): Directory to start recursive search if needed. Defaults to ".".

    Returns:
        Union[Path, str, List[Path]]: Resolved absolute Path if single match, list of Paths if multiple matches, or error string.
    """
    try:
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
    except Exception as e:
        return f"Error resolving file path '{file_path}': {str(e)}"

def readFile(filename: str, target_directory: Union[str, Path] = ".") -> str:
    """
    Find a file and read its content as text.

    Args:
        filename (str): Name or path of the file to read.
        target_directory (Union[str, Path]): Directory to search if file is not found directly. Defaults to ".".

    Returns:
        str: File content as a string, list of candidate matches, or error message.
    """
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
    Write content to a file, creating parent directories if necessary.

    Args:
        filename (str): Name or path of the destination file.
        content (str): Text content to write into the file.
        mode (str): File open mode. Defaults to "w".
        target_directory (Union[str, Path]): Directory root for resolving relative paths. Defaults to ".".

    Returns:
        str: Success message or error description.
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
    Find a file and replace a specific block of code with new code in-place.

    Args:
        file_path (Union[str, Path]): Path or filename to modify.
        old_code (str): Exact existing snippet to replace.
        new_code (str): New replacement code snippet.
        target_directory (Union[str, Path]): Directory root for locating the file. Defaults to ".".

    Returns:
        str: Success message with diff preview of changes, or error description.
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
    """
    Dispatch and execute a requested file operation.

    Args:
        operation (str): Name of the operation ('find_file', 'read_file', 'write_file', 'replace_content').
        filename (str): Name of the file. Defaults to "".
        file_path (Union[str, Path]): Path to the file. Defaults to "".
        content (str): Content string for write operations. Defaults to "".
        old_code (str): Existing code block for replacement. Defaults to "".
        new_code (str): New code block for replacement. Defaults to "".
        target_directory (Union[str, Path]): Root search directory. Defaults to ".".

    Returns:
        Union[str, List[str]]: Operation output, list of paths for search, or error message.
    """
    try:
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
    except Exception as e:
        return f"Error executing file operation '{operation}': {str(e)}"



