import json
from pathlib import Path

def get_all_paths(root_path="."):
    root = Path(root_path)

    ignored_dirs = {
        "node_modules", ".venv", "venv", "__pycache__", ".git",
        ".idea", ".vscode", "dist", "build", ".next",
        ".pytest_cache", ".mypy_cache", ".ruff_cache",
    }

    ignored_files = {
        ".env", ".env.local", ".env.development",
        ".env.production", ".DS_Store",
    }

    all_paths = []
    for path in root.rglob("*"):
        relative_path = path.relative_to(root)
        if any(part in ignored_dirs for part in relative_path.parts):
            continue
        if path.is_file() and (path.name in ignored_files or path.name.endswith((".pyc", ".pyo"))):
            continue

        path_str = str(path)
        if len(path_str) > 400:
            path_str = path_str[:397] + "..."

        all_paths.append(path_str)

    return json.dumps(all_paths, indent=4)

if __name__ == "__main__":
    paths_json = get_all_paths()
    print(paths_json)