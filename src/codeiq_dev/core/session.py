import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Default session storage path: C:\Users\<username>\.codeiq\sessions
SESSIONS_DIR = Path.home() / ".codeiq" / "sessions"


def _ensure_sessions_dir() -> Path:
    """
    Ensure the target sessions directory exists on disk and return its path.

    Args:
        None

    Returns:
        Path: Path object pointing to the initialized sessions directory.
    """
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    return SESSIONS_DIR


def get_project_name() -> str:
    """
    Return the current project folder name.

    Args:
        None

    Returns:
        str: Name of the current working directory.
    """
    return Path.cwd().name


def get_session_file_path(session_id: str) -> Path:
    """
    Compute and return the absolute filesystem path for a given session identifier.

    Args:
        session_id (str): The unique session ID string or file name stem.

    Returns:
        Path: Full absolute file path for the session's JSON file.
    """
    name = session_id if session_id.endswith(".json") else f"{session_id}.json"
    return SESSIONS_DIR / name


def create_session(model: Optional[str] = None, save: bool = True) -> Dict[str, Any]:
    """
    Initialize a new chat session data structure matching standard schema, write to disk, and return it.

    Initial session ID uses a short hex UUID (8 chars) with project name prefix.
    When a title is generated, the file and ID can be renamed accordingly.

    Args:
        model (Optional[str]): AI model identifier to associate with the session. Defaults to None.

    Returns:
        Dict[str, Any]: Dictionary containing initialized session schema and empty message list.
    """
    _ensure_sessions_dir()
    short_uuid = uuid.uuid4().hex[:8]
    project_name = get_project_name()
    session_id = f"{project_name}-{short_uuid}"
    now_iso = datetime.now().isoformat()

    session_data: Dict[str, Any] = {
        "session_id": session_id,
        "title": "New Session",
        "model_name": model or "unknown",
        "messages": [],
        "session_prompt_tokens": 0,
        "session_completion_tokens": 0,
        "session_requests": 0,
        "total_tokens": 0,
        "project_name": project_name,
        "status": "active",
        "is_deleted": False,
        "deleted_at": None,
        "created_at": now_iso,
        "updated_at": now_iso,
    }

    if save:
        save_session(session_data)
    return session_data


def load_session(session_id: str) -> Dict[str, Any]:
    """
    Load a session dictionary from disk by exact session ID or unique prefix.

    If the requested session cannot be located or parsed, a new session is initialized and returned.

    Args:
        session_id (str): The session identifier or prefix to look up and load.

    Returns:
        Dict[str, Any]: Loaded session data dictionary or newly generated session data.
    """
    _ensure_sessions_dir()
    file_path = find_session_file(session_id, allow_deleted=True)
    if file_path and file_path.exists():
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Backward compatibility for legacy schema
                if "session_prompt_tokens" not in data:
                    t_info = data.get("token_usage", {})
                    data["session_prompt_tokens"] = t_info.get("query_tokens", 0)
                    data["session_completion_tokens"] = t_info.get("completion_tokens", 0)
                    data["total_tokens"] = t_info.get("session_tokens", 0)
                if "model_name" not in data:
                    data["model_name"] = data.get("model", "unknown")
                if "project_name" not in data:
                    data["project_name"] = get_project_name()
                if "title" not in data:
                    data["title"] = "Untitled Session"
                return data
        except Exception:
            pass

    return create_session()


def save_session(session_data: Dict[str, Any]) -> None:
    """
    Persist session data dictionary to its corresponding JSON file on disk.

    Args:
        session_data (Dict[str, Any]): Session dictionary containing metadata, messages, and token usage.

    Returns:
        None
    """
    _ensure_sessions_dir()
    session_id = session_data.get("session_id", "session_unknown")
    file_path = get_session_file_path(session_id)
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(session_data, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def append_message(session_data: Dict[str, Any], message: Dict[str, Any]) -> None:
    """
    Append a new conversation message (user, assistant, or tool) to the session and save to disk.

    Args:
        session_data (Dict[str, Any]): The in-memory session data dictionary to update.
        message (Dict[str, Any]): The message dictionary with role, content, and optional tool calls.

    Returns:
        None
    """
    session_data.setdefault("messages", []).append(message)
    session_data["updated_at"] = datetime.now().isoformat()
    save_session(session_data)


def update_tokens(
    session_data: Dict[str, Any],
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    increment_requests: bool = True,
) -> None:
    """
    Update cumulative token usage metrics and request count in the session and write changes to disk.

    Args:
        session_data (Dict[str, Any]): The in-memory session data dictionary to update.
        prompt_tokens (int): Cumulative or current prompt tokens consumed.
        completion_tokens (int): Cumulative or current completion tokens generated.
        total_tokens (int): Combined token count for the session.
        increment_requests (bool): Whether to increment session_requests by 1. Defaults to True.

    Returns:
        None
    """
    session_data["session_prompt_tokens"] = prompt_tokens
    session_data["session_completion_tokens"] = completion_tokens
    session_data["total_tokens"] = total_tokens
    if increment_requests:
        session_data["session_requests"] = session_data.get("session_requests", 0) + 1
    session_data["updated_at"] = datetime.now().isoformat()
    save_session(session_data)


def set_model(session_data: Dict[str, Any], model_name: str) -> None:
    """
    Record or update the active AI model name in the session metadata and save.

    Args:
        session_data (Dict[str, Any]): The session dictionary to update.
        model_name (str): The identifier string of the selected model.

    Returns:
        None
    """
    session_data["model_name"] = model_name
    session_data["updated_at"] = datetime.now().isoformat()
    save_session(session_data)


def update_session_title(session_data: Dict[str, Any], ai_title: str) -> str:
    """
    Update session with an AI-generated title and rename the stored JSON file to <projectName>-<sessionTitle>.

    Args:
        session_data (Dict[str, Any]): The session dictionary to update and rename.
        ai_title (str): The plain title string generated by AI (e.g. 'Auto Compaction Not Triggering').

    Returns:
        str: The updated session_id (e.g. 'my-cli-agent-Auto Compaction Not Triggering').
    """
    _ensure_sessions_dir()
    old_id = session_data.get("session_id", "")
    old_path = get_session_file_path(old_id)

    # Sanitize title for filename
    clean_title = "".join(c for c in ai_title if c.isalnum() or c in (" ", "-", "_")).strip()
    if not clean_title:
        clean_title = "Session"

    project_name = session_data.get("project_name") or get_project_name()
    new_id = f"{project_name}-{clean_title}"
    new_path = get_session_file_path(new_id)

    session_data["title"] = ai_title
    session_data["session_id"] = new_id
    session_data["updated_at"] = datetime.now().isoformat()

    # Save to the new filename
    save_session(session_data)

    # If the file path changed and old file exists, remove the old one
    if old_path.exists() and old_path != new_path:
        try:
            old_path.unlink()
        except Exception:
            pass

    return new_id


def close_session(session_id: str) -> Optional[str]:
    """
    Mark a session status as closed while preserving its chat history on disk.

    Args:
        session_id (str): The identifier or prefix of the session to close.

    Returns:
        Optional[str]: The session ID string if found and closed, or None if not found.
    """
    file_path = find_session_file(session_id, allow_deleted=True)
    if not file_path:
        return None
    session_data = load_session(file_path.stem)
    session_data["status"] = "closed"
    session_data["updated_at"] = datetime.now().isoformat()
    save_session(session_data)
    return session_data["session_id"]


def soft_delete_session(session_id: str) -> Optional[str]:
    """
    Soft-delete a session, hiding it from listings and preventing resumption without purging data.

    Args:
        session_id (str): The identifier or prefix of the session to soft-delete.

    Returns:
        Optional[str]: The session ID string if found and soft-deleted, or None if not found.
    """
    file_path = find_session_file(session_id, allow_deleted=True)
    if not file_path:
        return None
    session_data = load_session(file_path.stem)
    session_data["is_deleted"] = True
    session_data["deleted_at"] = datetime.now().isoformat()
    session_data["updated_at"] = datetime.now().isoformat()
    save_session(session_data)
    return session_data["session_id"]


def restore_session(session_id: str) -> Optional[str]:
    """
    Restore a previously soft-deleted session back to active visibility.

    Args:
        session_id (str): The identifier or prefix of the soft-deleted session to restore.

    Returns:
        Optional[str]: The session ID string if restored, or None if not found.
    """
    file_path = find_session_file(session_id, allow_deleted=True)
    if not file_path:
        return None
    session_data = load_session(file_path.stem)
    session_data["is_deleted"] = False
    session_data["deleted_at"] = None
    session_data["updated_at"] = datetime.now().isoformat()
    save_session(session_data)
    return session_data["session_id"]


def list_sessions(include_deleted: bool = False) -> List[Dict[str, Any]]:
    """
    List all saved sessions sorted by most recently updated first.

    Args:
        include_deleted (bool): If True, include soft-deleted sessions in the list. Defaults to False.

    Returns:
        List[Dict[str, Any]]: List of session summary dictionaries containing ID, timestamps, status, model, and message count.
    """
    if not SESSIONS_DIR.exists():
        return []

    sessions = []
    for file in SESSIONS_DIR.glob("*.json"):
        try:
            with open(file, "r", encoding="utf-8") as f:
                meta = json.load(f)

            is_del = bool(meta.get("is_deleted", False))
            if is_del and not include_deleted:
                continue

            first_prompt = next(
                (
                    m["content"]
                    for m in meta.get("messages", [])
                    if m.get("role") == "user" and isinstance(m.get("content"), str)
                ),
                "Empty session",
            )
            sessions.append(
                {
                    "session_id": meta.get("session_id", file.stem),
                    "title": meta.get("title", file.stem),
                    "project_name": meta.get("project_name", ""),
                    "created_at": meta.get("created_at", ""),
                    "updated_at": meta.get("updated_at", ""),
                    "status": meta.get("status", "active"),
                    "is_deleted": is_del,
                    "deleted_at": meta.get("deleted_at"),
                    "model_name": meta.get("model_name") or meta.get("model", "unknown"),
                    "total_tokens": meta.get("total_tokens", 0),
                    "session_requests": meta.get("session_requests", 0),
                    "first_prompt": (first_prompt[:60] + "...")
                    if len(first_prompt) > 60
                    else first_prompt,
                    "message_count": len(meta.get("messages", [])),
                }
            )
        except Exception:
            continue

    sessions.sort(key=lambda s: s.get("updated_at", ""), reverse=True)
    return sessions


def find_session_file(session_id: str, allow_deleted: bool = False) -> Optional[Path]:
    """
    Search for a session JSON file matching the provided session ID or unique prefix.

    Args:
        session_id (str): Exact session ID, filename stem, or unique prefix.
        allow_deleted (bool): Whether to consider soft-deleted sessions. Defaults to False.

    Returns:
        Optional[Path]: Absolute Path to the matching JSON file, or None if not found.
    """
    if not SESSIONS_DIR.exists():
        return None

    def _is_valid(path: Path) -> bool:
        if allow_deleted:
            return True
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return not bool(data.get("is_deleted", False))
        except Exception:
            return True

    # Exact filename match
    exact = SESSIONS_DIR / (session_id if session_id.endswith(".json") else f"{session_id}.json")
    if exact.exists() and _is_valid(exact):
        return exact

    # Case-insensitive or prefix match
    matches = [
        f
        for f in SESSIONS_DIR.glob("*.json")
        if (f.stem.startswith(session_id) or session_id.lower() in f.stem.lower()) and _is_valid(f)
    ]
    if len(matches) == 1:
        return matches[0]
    elif len(matches) > 1:
        # Prefer prefix match
        prefix_matches = [f for f in matches if f.stem.startswith(session_id)]
        if prefix_matches:
            return prefix_matches[0]
        return matches[0]
    return None


def purge_deleted_sessions(session_id: Optional[str] = None) -> List[str]:
    """
    Permanently delete soft-deleted session JSON files from the filesystem.

    Args:
        session_id (Optional[str]): If provided, only purges that specific soft-deleted session.
            If None, purges all soft-deleted sessions found in the directory.

    Returns:
        List[str]: List of session ID strings permanently deleted from disk.
    """
    if not SESSIONS_DIR.exists():
        return []

    purged: List[str] = []
    if session_id:
        file = find_session_file(session_id, allow_deleted=True)
        if file and file.exists():
            try:
                with open(file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if bool(data.get("is_deleted", False)):
                    file.unlink()
                    purged.append(file.stem)
            except Exception:
                pass
    else:
        for file in SESSIONS_DIR.glob("*.json"):
            try:
                with open(file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if bool(data.get("is_deleted", False)):
                    file.unlink()
                    purged.append(file.stem)
            except Exception:
                continue

    return purged
