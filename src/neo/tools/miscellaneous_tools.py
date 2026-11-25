import ast
import os
import re
import signal
import subprocess
import shlex # Splits shell commands into individual arguments safely for inspection.
from pathlib import Path
from typing import Optional
import typer
from rich.console import Console
from neo.tools.file_tools import findFile
from neo.core.guardrails import EnvGuardrail

console = Console()

# Set of commands/prefixes that represent continuous or long-running interactive processes
BLOCKED_PATTERNS = {
    # Continuous / monitoring / interactive
    "watch", "top", "htop",
    # Servers / Dev runners
    "npm start", "npm run dev", "npm run serve", "yarn start", "yarn dev",
    "pnpm dev", "pnpm start", "vite", "nodemon", "next dev",
    "flask run", "uvicorn", "gunicorn", "streamlit run",
    "python -m http.server", "http-server",
    # Shells / REPLs without args
    "bash", "sh", "zsh", "powershell", "cmd", "ipython"
}

MAX_OUTPUT_LENGTH = 350
DEFAULT_TIMEOUT_SECONDS = 15
MAX_TIMEOUT_SECONDS = 15

# Patterns that spawn detached/background processes
DETACH_PATTERNS = (
    "nohup ",
    "disown",
    "start-process",
    "cmd /c start",
    "screen ",
    "tmux ",
)


def is_continuous_or_long_running(command: str) -> bool:
    """
    Check if a command represents a continuous, interactive, or long-running process.

    Args:
        command (str): Command line string to inspect.

    Returns:
        bool: True if the command is continuous or long-running, False otherwise.
    """
    cmd_clean = command.strip().lower()

    # Exact or prefixed match for known servers/tools
    for pattern in BLOCKED_PATTERNS:
        if cmd_clean == pattern or cmd_clean.startswith(f"{pattern} "):
            return True

    # Reject background/detached process spawners
    if any(p in cmd_clean for p in DETACH_PATTERNS):
        return True
    if re.search(r"(?:^|\s)&(?!&)\s*$", cmd_clean):
        return True

    try:
        parts = shlex.split(cmd_clean)
    except Exception:
        parts = cmd_clean.split()

    if not parts:
        return False


def has_long_running_python_code(script_path: Path) -> Optional[str]:
    """
    Inspect a Python script for obvious infinite loops, servers, or long sleeps.

    Args:
        script_path (Path): Path to the Python file to inspect.

    Returns:
        Optional[str]: Reason string if long-running code is detected, else None.
    """
    try:
        source = script_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None

    for node in ast.walk(tree):
        # Detect `while True:` or `while 1:`
        if isinstance(node, ast.While) and isinstance(node.test, ast.Constant):
            if node.test.value in (True, 1):
                return "infinite loop (`while True` / `while 1`)"

        if isinstance(node, ast.Call):
            func_name = ""
            if isinstance(node.func, ast.Attribute):
                func_name = node.func.attr
            elif isinstance(node.func, ast.Name):
                func_name = node.func.id

            if func_name in {"serve_forever", "run_forever"}:
                return f"server loop (`{func_name}`)"

            if func_name == "sleep" and node.args:
                arg0 = node.args[0]
                if isinstance(arg0, ast.Constant) and isinstance(arg0.value, (int, float)):
                    if arg0.value > MAX_TIMEOUT_SECONDS:
                        return f"long sleep (`sleep({arg0.value})` > {MAX_TIMEOUT_SECONDS}s)"

    return None


def _kill_process_tree(proc: subprocess.Popen) -> None:
    """Terminate a process and all of its spawned child processes."""
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
            capture_output=True,
        )
    else:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        proc.kill()
        proc.wait(timeout=2)
    except Exception:
        pass


def has_long_running_python_code(script_path: Path) -> Optional[str]:
    """
    Inspect a Python script for obvious infinite loops, servers, or long sleeps.

    Args:
        script_path (Path): Path to the Python file to inspect.

    Returns:
        Optional[str]: Reason string if long-running code is detected, else None.
    """
    try:
        source = script_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None

    for node in ast.walk(tree):
        # Detect `while True:` or `while 1:`
        if isinstance(node, ast.While) and isinstance(node.test, ast.Constant):
            if node.test.value in (True, 1):
                return "infinite loop (`while True` / `while 1`)"

        if isinstance(node, ast.Call):
            func_name = ""
            if isinstance(node.func, ast.Attribute):
                func_name = node.func.attr
            elif isinstance(node.func, ast.Name):
                func_name = node.func.id

            if func_name in {"serve_forever", "run_forever"}:
                return f"server loop (`{func_name}`)"

            if func_name == "sleep" and node.args:
                arg0 = node.args[0]
                if isinstance(arg0, ast.Constant) and isinstance(arg0.value, (int, float)):
                    if arg0.value > MAX_TIMEOUT_SECONDS:
                        return f"long sleep (`sleep({arg0.value})` > {MAX_TIMEOUT_SECONDS}s)"

    return None


def _kill_process_tree(proc: subprocess.Popen) -> None:
    """Terminate a process and all of its spawned child processes."""
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
            capture_output=True,
        )
    else:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        proc.kill()
        proc.wait(timeout=2)
    except Exception:
        pass


def truncate_output(text: str, max_length: int = MAX_OUTPUT_LENGTH) -> str:
    """
    Truncate terminal output text to approximately max_length characters with an indicator.

    Args:
        text (str): String output to inspect and truncate if necessary.
        max_length (int): Maximum character limit. Defaults to MAX_OUTPUT_LENGTH (350).

    Returns:
        str: Truncated output string with omission notice if truncated.
    """
    if len(text) <= max_length:
        return text
    truncated = text[:max_length].rstrip()
    return f"{truncated}\n... [Output truncated to ~{max_length} characters]"


def executeTool(
    command: str,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    ask_confirm: bool = True,
    cwd: Optional[str] = None,
) -> str:
    """
    Executes a short-running, non-continuous shell command using subprocess.
    Prompts the user for confirmation before executing.
    Captures command output and truncates it to ~350 characters if necessary.

    Args:
        command (str): Shell command to execute.
        timeout (int): Timeout in seconds to enforce non-continuous termination.
        ask_confirm (bool): Whether to prompt the user for confirmation.
        cwd (str, optional): Directory to execute the command in.

    Returns:
        str: Captured command output (or error/cancellation message), truncated to ~350 chars.
    """
    cmd = command.strip()
    if not cmd:
        return "Error: No command provided."

    # Enforce hard upper bound on execution timeout
    timeout = max(1, min(int(timeout), MAX_TIMEOUT_SECONDS))

    if is_continuous_or_long_running(cmd):
        return (
            f"Execution rejected: '{cmd}' is a long-running, continuous, or interactive command. "
            "executeTool only supports short-running commands."
        )

    # Protect .env files from being inspected or dumped via terminal commands (cat, type, echo, grep, etc.)
    cmd_lower = cmd.lower()
    if any(env_token in cmd_lower for env_token in (".env", ".env.", "env.local", "env.production", "secrets.json", "credentials.json")):
        # Check if it targets reading or displaying the env file
        for inspect_cmd in ("cat", "type", "get-content", "gc", "more", "head", "tail", "grep", "findstr", "sed", "awk", "python", "node"):
            if inspect_cmd in cmd_lower:
                return "Execution rejected: Accessing or displaying .env and sensitive environment files is strictly restricted by security guardrail."

    # Automatically resolve script path if user executes e.g. 'python cli.py' from root directory
    try:
        parts = shlex.split(cmd, posix=(os.name != "nt"))
        if len(parts) >= 2 and parts[0].lower() in {"python", "python3", "py"}:
            script_candidate = Path(parts[1])
            search_dir = cwd if cwd else "."
            if not (Path(search_dir) / script_candidate).exists() and not script_candidate.is_absolute():
                matches = findFile(target_directory=search_dir, filename=str(script_candidate))
                if matches:
                    resolved_script = str(matches[0])
                    # Reconstruct command with resolved script path
                    parts[1] = f'"{resolved_script}"' if " " in resolved_script else resolved_script
                    cmd = " ".join(parts)
                    script_candidate = Path(resolved_script)
            else:
                script_candidate = Path(search_dir) / script_candidate if not script_candidate.is_absolute() else script_candidate

            if script_candidate.exists() and script_candidate.suffix.lower() == ".py":
                reason = has_long_running_python_code(script_candidate)
                if reason:
                    return (
                        f"Execution rejected: '{script_candidate.name}' contains {reason}. "
                        "Long-running scripts are not permitted."
                    )
    except Exception:
        pass

    # Ask user confirmation before executing
    if ask_confirm:
        console.print(f"\n[bold yellow]Command to execute:[/bold yellow] [bold cyan]{cmd}[/bold cyan]")
        if cwd:
            console.print(f"[dim]Working directory: {cwd}[/dim]")
        confirmed = typer.confirm("Do you want to execute this command?", default=False)
        if not confirmed:
            return "Command execution cancelled by user."

    proc: Optional[subprocess.Popen] = None
    try:
        popen_kwargs = {
            "shell": True,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "text": True,
            "cwd": cwd,
        }
        if os.name != "nt":
            popen_kwargs["start_new_session"] = True

        proc = subprocess.Popen(cmd, **popen_kwargs)
        stdout_raw, stderr_raw = proc.communicate(timeout=timeout)

        stdout = stdout_raw.strip() if stdout_raw else ""
        stderr = stderr_raw.strip() if stderr_raw else ""

        if proc.returncode == 0:
            output = stdout or "Command executed successfully with no output."
        else:
            output_parts = []
            if stdout:
                output_parts.append(f"STDOUT:\n{stdout}")
            if stderr:
                output_parts.append(f"STDERR:\n{stderr}")
            output = f"Command failed (code {proc.returncode}):\n" + ("\n".join(output_parts) if output_parts else "No output captured.")

        # Scrub any secrets from terminal command output before returning
        masked_output = EnvGuardrail.mask_text(output)
        return truncate_output(masked_output, MAX_OUTPUT_LENGTH)

    except subprocess.TimeoutExpired:
        if proc is not None:
            _kill_process_tree(proc)
        return f"Error: Command timed out after {timeout} seconds. Long-running processes are not permitted."
    except Exception as e:
        return f"Error executing command: {str(e)}"
