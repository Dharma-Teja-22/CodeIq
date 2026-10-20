"""Terminal shell execution tools with safety detection."""

from __future__ import annotations
import asyncio
import os
from pathlib import Path
import subprocess
import time
from typing import Dict, Optional, Tuple

RISKY_COMMAND_PATTERNS = [
    r"\brm\s+-[rf]+",
    r"\bdel\s+/[sfq]+",
    r"\bformat\b",
    r"\bdrop\s+database\b",
    r"\bkill\b",
    r"\bkillall\b",
    r"\bshutdown\b",
    r"\breboot\b",
    r"\bgit\s+reset\s+--hard\b",
    r"\bgit\s+clean\s+-[xfd]+",
    r"\bgit\s+push\s+.*--force\b",
    r"\bcurl.*\|\s*sh\b",
    r"\bwget.*\|\s*sh\b",
    r"\bmkfs\b",
    r"\bdd\s+if=",
]


def is_risky_command(command: str) -> bool:
    import re
    cmd_lower = command.lower()
    for pattern in RISKY_COMMAND_PATTERNS:
        if re.search(pattern, cmd_lower):
            return True
    return False


def execute_command_sync(
    command: str,
    cwd: Optional[Path] = None,
    timeout: int = 60,
) -> Tuple[int, str]:
    """Synchronous execution of a shell command."""
    work_dir = str(cwd or Path.cwd())
    start_time = time.time()

    is_windows = os.name == "nt"
    shell_cmd = ["powershell", "-NoProfile", "-Command", command] if is_windows else ["bash", "-c", command]

    try:
        proc = subprocess.run(
            shell_cmd,
            cwd=work_dir,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
            encoding="utf-8",
            errors="replace",
        )
        elapsed = round(time.time() - start_time, 2)
        stdout = proc.stdout.strip()
        stderr = proc.stderr.strip()

        output_parts = []
        if stdout:
            output_parts.append(stdout)
        if stderr:
            output_parts.append(f"[STDERR]\n{stderr}")

        full_output = "\n".join(output_parts) if output_parts else "(No output produced)"
        formatted = f"{full_output}\n\n[Process completed with exit code {proc.returncode} in {elapsed}s]"
        return proc.returncode, formatted

    except subprocess.TimeoutExpired:
        return 124, f"Error: Command timed out after {timeout} seconds."
    except Exception as e:
        return 1, f"Execution failed: {str(e)}"


async def execute_command_async(
    command: str,
    cwd: Optional[Path] = None,
    timeout: int = 60,
) -> Tuple[int, str]:
    """Asynchronous command execution for event loops."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, execute_command_sync, command, cwd, timeout)
