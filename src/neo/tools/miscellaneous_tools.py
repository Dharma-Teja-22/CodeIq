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
DEFAULT_TIMEOUT_SECONDS = 30


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

    try:
        parts = shlex.split(cmd_clean)
    except Exception:
        parts = cmd_clean.split()

    if not parts:
        return False

    first = parts[0]
    # Block python/node/etc when invoked without any script or code args (interactive shell)
    if first in {"python", "python3", "py", "node", "ruby", "perl", "php"}:
        if len(parts) == 1:
            return True

    return False


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
        parts = shlex.split(cmd)
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

    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
        )

        stdout = result.stdout.strip() if result.stdout else ""
        stderr = result.stderr.strip() if result.stderr else ""

        if result.returncode == 0:
            output = stdout or "Command executed successfully with no output."
        else:
            output_parts = []
            if stdout:
                output_parts.append(f"STDOUT:\n{stdout}")
            if stderr:
                output_parts.append(f"STDERR:\n{stderr}")
            output = f"Command failed (code {result.returncode}):\n" + ("\n".join(output_parts) if output_parts else "No output captured.")

        # Scrub any secrets from terminal command output before returning
        masked_output = EnvGuardrail.mask_text(output)
        return truncate_output(masked_output, MAX_OUTPUT_LENGTH)

    except subprocess.TimeoutExpired:
        return f"Error: Command timed out after {timeout} seconds. Long-running processes are not permitted."
    except Exception as e:
        return f"Error executing command: {str(e)}"
