from codeiq_dev.tools.git_tools import *
from codeiq_dev.tools.file_tools import fileOperation
from codeiq_dev.tools.miscellaneous_tools import executeTool
import asyncio
import sys
from openai import AsyncOpenAI
from dotenv import load_dotenv
import os
import sys
from pathlib import Path
import typer
from rich.console import Console
from rich.text import Text
import json

import msvcrt

load_dotenv()
app = typer.Typer()
console = Console()

# 5 supported models
AVAILABLE_MODELS = [
    "gemini-flash-latest",
    "gemini-3.1-pro-preview",
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash-lite",
    "gemini-3.8-flash",
]

DEFAULT_MODEL = "gemini-3.5-flash-lite"
CONFIG_FILE = Path(".codeiq_config.json")


def get_selected_model() -> str:
    """
    Retrieve currently selected model ID.
    Priority:
    1. Session environment variable `MODEL` (e.g. set MODEL=... or $env:MODEL=...)
    2. Persisted config file (`.codeiq_config.json`)
    3. Default fallback model (`DEFAULT_MODEL`)
    """
    # 1. Environment variable for the current terminal session
    env_model = os.getenv("MODEL")
    if env_model:
        # Strip potential surrounding quotes from shells (e.g. 'model' or "model")
        cleaned_env_model = env_model.strip().strip("'").strip('"')
        if cleaned_env_model in AVAILABLE_MODELS:
            return cleaned_env_model

    # 2. Persisted configuration file
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                configured = data.get("model")
                if configured and configured in AVAILABLE_MODELS:
                    return configured
        except Exception:
            pass

    # 3. Default fallback
    return DEFAULT_MODEL


def set_selected_model(model_name: str) -> None:
    """Save selected model to config file."""
    data = {}
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}
    data["model"] = model_name
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def select_model_interactive(options: list[str], default_option: str) -> str:
    """
    Renders an interactive arrow-key selection list (like npm create vite).
    Allows navigating using UP/DOWN arrow keys and selecting with ENTER.
    """
    # Enable Windows VT100 / ANSI escape sequence processing in cmd.exe
    os.system("")

    current_idx = options.index(default_option) if default_option in options else 0

    # Hide cursor during interactive selection to eliminate flickering
    sys.stdout.write("\033[?25l")
    sys.stdout.flush()

    def build_menu() -> str:
        lines = []
        for idx, opt in enumerate(options):
            is_active = (idx == current_idx)
            is_def = (opt == default_option)
            cursor = ">" if is_active else " "
            def_tag = " (default)" if is_def else ""

            if is_active:
                lines.append(f"\033[2K\033[36m\033[1m {cursor} {opt}{def_tag}\033[0m")
            else:
                lines.append(f"\033[2K   {opt}{def_tag}")
        return "\n".join(lines) + "\n"

    try:
        console.print("[dim]? Select a model (Use arrow keys or enter number, press Enter to confirm):[/dim]")
        # Reserve lines once
        sys.stdout.write("\n" * len(options))
        sys.stdout.write(f"\033[{len(options)}A")
        sys.stdout.write(build_menu())
        sys.stdout.flush()

        while True:
            key = msvcrt.getch()
            # Special/extended key prefix (e.g. arrow keys)
            if key in (b"\x00", b"\xe0"):
                arrow = msvcrt.getch()
                if arrow == b"H":  # Up arrow
                    current_idx = (current_idx - 1) % len(options)
                elif arrow == b"P":  # Down arrow
                    current_idx = (current_idx + 1) % len(options)
                else:
                    continue
                # Move back up and redraw in a single atomic write
                sys.stdout.write(f"\033[{len(options)}A" + build_menu())
                sys.stdout.flush()
            elif key in (b"\r", b"\n"):  # Enter key
                break
            elif key == b"\x03":  # Ctrl+C
                raise KeyboardInterrupt
            elif key.isdigit():
                num = int(key.decode()) - 1
                if 0 <= num < len(options):
                    current_idx = num
                    sys.stdout.write(f"\033[{len(options)}A" + build_menu())
                    sys.stdout.flush()

        return options[current_idx]
    finally:
        # Restore visible cursor
        sys.stdout.write("\033[?25h")
        sys.stdout.flush()


# On Windows, silence the known Proactor transport __del__ bug on loop close
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

client = AsyncOpenAI(
    api_key=os.getenv("GEMINI_API_KEY"),
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
)

# Tools

tools = [
    {
        "type": "function",
        "function": {
            "name": "gitOperations",
            "description": (
                "Perform Git operations in the current repository. Add: Add a single file, multiple files, or all new, modified, and deleted files to Git. For example, add app.py or add all the latest code changes. Commit: Save the staged changes with a commit message. For example, commit with message Initial setup. Push: Upload committed changes to the remote repository on the current branch. For example, push my changes. Pull: Get the latest changes from the remote repository into the current branch. For example, pull the latest changes. Branch: Show the name of the current Git branch. For example, which branch am I working on. Choose the correct operation based on the user's request."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": [
                            "add",
                            "commit",
                            "push",
                            "pull",
                            "branch"
                        ],
                        "description": "The Git operation to perform."
                    },
                    "file_name": {
                        "type": "string",
                        "description": (
                            "File or directory to stage. "
                            "Use '.' for all changes."
                        )
                    },
                    "commit_message": {
                        "type": "string",
                        "description": "Message to use for a commit."
                    }
                },
                "required": ["operation"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "fileOperations",
            "description": (
                "Perform file operations in the project. "
                "read_file: Read content of a file. "
                "write_file: Write or create a completely new file when explicitly requested. DO NOT use write_file to duplicate an existing file when fixing errors. "
                "replace_content: Replace an existing specific block of code in an existing file with corrected or updated code. "
                "find_file: Search for a file by name."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": ["read_file", "write_file", "replace_content", "find_file"],
                        "description": "The file operation to perform."
                    },
                    "file_path": {
                        "type": "string",
                        "description": "Relative or absolute path to the file (e.g. 'src/app.py' or 'app.py')."
                    },
                    "content": {
                        "type": "string",
                        "description": "Content to write (for write_file)."
                    },
                    "old_code": {
                        "type": "string",
                        "description": "Exact existing code snippet to be replaced (for replace_content)."
                    },
                    "new_code": {
                        "type": "string",
                        "description": "New replacement code snippet (for replace_content)."
                    }
                },
                "required": ["operation", "file_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "executeTool",
            "description": (
                "Execute a single short-running, non-interactive terminal command in the user's project environment. This tool is intended for operations that complete quickly and return a finite output, such as listing files, inspecting project structure, checking Git status, installing specific packages, running unit tests, checking dependency versions, or executing short scripts. Before execution, always present the exact generated command to the user and obtain explicit confirmation. Never execute a command without approval. Do not use this tool for continuous, background, interactive, persistent, or long-running processes, including development servers, production servers, file watchers, monitoring utilities, interactive shells, REPL sessions, or commands that wait indefinitely for input. Examples of prohibited commands include npm start, npm run dev, yarn dev, pnpm dev, vite, nodemon, next dev, uvicorn, gunicorn, flask run, streamlit run, watch, top, htop, and tail -f. Never bypass these restrictions through command chaining, shell wrappers, or background execution. If the requested operation requires a continuous or long-running process, inform the user that it is not supported instead of invoking this tool. Execute only commands directly related to the user's request, enforce the configured execution timeout, and report the execution result clearly. If execution fails or times out, communicate the error without automatically retrying. Keep the returned output concise and limit it to approximately 350 characters, clearly indicating when the output has been truncated."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The exact, complete terminal command that needs to be executed. Provide only one short-running, non-interactive command that is directly relevant to the user's request and is expected to complete within the configured timeout. Do not include explanations, Markdown formatting, or additional instructions. Avoid destructive or irreversible operations unless explicitly authorized. Do not provide commands that start servers, background processes, watchers, monitoring utilities, interactive shells, REPL sessions, infinite loops, or processes that require continuous execution. Do not chain multiple commands using &&, ||, ;, pipes, or shell wrappers to bypass execution restrictions. The command must be suitable for execution in the user's project environment and must be presented to the user for explicit approval before execution."
                    }
                },
                "required": ["command"]
            }
        }
    }
]

# Async chat implementation
async def _chat():
    """Interactive CodeIq chat with Git and File tools using asyncio."""
    while True:
        prompt = await asyncio.to_thread(
            typer.prompt,
            typer.style("User", fg=typer.colors.CYAN, bold=True),
        )

        if prompt.strip().lower() in ("exit", "quit","bye","close"):
            console.print("[yellow]Chat ended.[/yellow]")
            break

        messages = [
            {
                "role": "system",
                "content": (
                    "You are CodeIq, a polite, helpful AI coding assistant that performs Git operations, File operations, and Command execution. Always choose the correct operation based on the user's request."
                    "For File Operations and Error Fixing: When the user asks you to run a file and fix/resolve its errors (e.g. 'run test.py file and resolve the issues'): "
                    "1. Always work directly on the target file itself. NEVER create a new or duplicate file (e.g., do NOT create payroll_app.py or test_fixed.py). "
                    "2. Read the file using read_file to inspect its code and understand its formatting. "
                    "3. When you identify bugs or after seeing test/run failures, use replace_content to apply fixes directly to that exact same file in-place, keeping sufficient context in old_code. "
                    "4. After modifying the file, run the target file again using executeTool to verify that all errors are resolved. "
                    "5. Inform the user clearly and politely: explain what errors were found, state that you updated the file in-place, and show that the rerun succeeded. "
                    "For Git Operations: Use add to stage new, modified, or deleted files, and use commit to save staged changes with a commit message. If the user asks to commit the latest added or staged files, select commit instead of add. If the user asks to add files and then commit them, perform add first and commit next. Use push to upload committed changes, pull to get the latest remote changes, and branch to show the current branch name. Never confuse these operations or claim success unless the tool result confirms it. "
                    "For Command Execution: When the user asks to run or execute a command in plain English (NLP query), generate the appropriate shell command and call executeTool. However, continuous or long-running commands (such as dev servers like 'npm start', 'npm run dev', 'vite', 'uvicorn', 'flask run', monitoring tools like 'top', 'htop', 'watch', 'tail -f', interactive REPLs/shells, etc.) are strictly prohibited. At the beginning itself, if the requested command is continuous or long-running, DO NOT call executeTool; instead, reply directly explaining politely that continuous and long-running processes are not supported. "
                    "Response Style after Command Execution: Rather than blindly dumping raw command output or duplicating what was already run, provide a polite, concise, and helpful assistant response tailored directly to what the user asked (e.g. summarizing key information, explaining what was fixed in-place, and confirming the outcome). If the user explicitly asks to see the raw output, provide only the relevant snippet cleanly formatted. "
                    "Security and Environment Protection: Never attempt to read, display, or disclose the contents of .env or sensitive environment configuration files. Do not call read_file or execute terminal commands to display .env files. If the user asks for .env contents or credentials, politely decline explaining that environment secrets are protected for security reasons. "
                    "Note: We do have multiple tool calls too. So if you need to perform multiple operations, call the tool for each operation sequentially. After a tool has executed and returned a result, always provide a concise summary or confirmation to the user."
                ),
            },
            {"role": "user", "content": prompt},
        ]

        status_text = "Thinking..."
        current_model = get_selected_model()
        # Inner loop handles all tool-calling rounds for this question.
        while True:
            try:
                with console.status(
                    f"[bold cyan]{status_text}[/bold cyan]",
                    spinner="arc",
                ):
                    response = await client.chat.completions.create(
                        model=current_model,
                        messages=messages,
                        tools=tools,
                        tool_choice="auto",
                    )
                assistant_message = response.choices[0].message
                # No more tool calls: display the final response.
                if not assistant_message.tool_calls:
                    content = (assistant_message.content or "").strip()
                    if not content and status_text != "Thinking...":
                        content = "Done."
                    if content:
                        console.print(
                            Text("Assistant:", style="bold cyan"),
                            Text(content, style="green"),
                        )
                    break

                # Preserve the assistant's tool-call message.
                messages.append(assistant_message.model_dump(exclude_none=True))

                cancelled = False

                # Execute all tool calls returned in this response.
                for tool_call in assistant_message.tool_calls:
                    try:
                        arguments = json.loads(tool_call.function.arguments)

                        if tool_call.function.name == "fileOperations":
                            operation = arguments.get("operation")
                            fpath = arguments.get("file_path", "")

                            # If find_file or operation returned multiple files, prompt user to choose
                            if operation == "find_file":
                                matches = await asyncio.to_thread(
                                    fileOperation, operation="find_file", file_path=fpath
                                )
                                if not matches:
                                    result = f"No files found matching '{fpath}'."
                                    console.print(f"[yellow]{result}[/yellow]")
                                elif len(matches) == 1:
                                    result = f"Found: {matches[0]}"
                                    console.print(f"[green]{result}[/green]")
                                else:
                                    console.print(f"\n[bold yellow]Multiple files found for '{fpath}':[/bold yellow]")
                                    for idx, match_path in enumerate(matches, 1):
                                        console.print(f"  [{idx}] {match_path}")
                                    choice = await asyncio.to_thread(
                                        typer.prompt, "Select file number to use", default="1"
                                    )
                                    try:
                                        selected_idx = int(choice) - 1
                                        selected_path = matches[selected_idx]
                                    except (ValueError, IndexError):
                                        selected_path = matches[0]
                                    result = f"Selected file: {selected_path}"
                                    console.print(f"[green]Using: {selected_path}[/green]")

                            elif operation == "read_file":
                                result = await asyncio.to_thread(
                                    fileOperation, operation="read_file", file_path=fpath
                                )
                                # Avoid dumping hundreds of lines onto the screen
                                line_count = len(result.splitlines())
                                console.print(f"[green]Read '{fpath}' ({line_count} lines loaded into context).[/green]")

                            elif operation == "replace_content":
                                console.print(f"[cyan]Applying code changes to '{fpath}'...[/cyan]")
                                old_snippet = arguments.get("old_code", "")
                                new_snippet = arguments.get("new_code", "")
                                result = await asyncio.to_thread(
                                    fileOperation,
                                    operation="replace_content",
                                    file_path=fpath,
                                    old_code=old_snippet,
                                    new_code=new_snippet,
                                )
                                if result.startswith("Error") or "not found" in result:
                                    console.print(f"[bold red]{result}[/bold red]")
                                else:
                                    console.print(f"[bold cyan]Changes applied to '{fpath}':[/bold cyan]")
                                    if old_snippet:
                                        for line in old_snippet.splitlines():
                                            console.print(f"[bold red]- {line}[/bold red]")
                                    if new_snippet:
                                        for line in new_snippet.splitlines():
                                            console.print(f"[bold green]+ {line}[/bold green]")

                            elif operation == "write_file":
                                result = await asyncio.to_thread(
                                    fileOperation,
                                    operation="write_file",
                                    file_path=fpath,
                                    content=arguments.get("content", ""),
                                )
                                console.print(f"[green]{result}[/green]")
                            else:
                                result = f"Unsupported file operation: {operation}"

                        elif tool_call.function.name == "gitOperations":
                            operation = arguments["operation"]
                            console.print(f"[cyan]Executing Git operation: {operation}[/cyan]")

                            if operation.lower() == "commit":
                                diff = await asyncio.to_thread(gitDiff)
                                if not diff or diff.startswith("Failed to get the diff"):
                                    result = diff or "No staged changes found."
                                else:
                                    # Pick the first 200 lines from the diff
                                    diff_lines = diff.splitlines()
                                    limited_diff = "\n".join(diff_lines[:200])
                                    prompt = f'''Generate a short, descriptive Git commit message based on the staged changes. Follow Conventional Commits format.
                                            Use one of these prefixes:
                                                - feat: for new functionality
                                                - fix: for bug fixes
                                                - refactor: for code restructuring
                                                - docs: for documentation changes
                                                - test: for test changes
                                                - perf: for performance improvements
                                                - chore: for maintenance tasks
                                                - style: for formatting changes

                                                Rules:
                                                - Use simple, clear English.
                                                - Start with the appropriate prefix.
                                                - Use lowercase after the prefix.
                                                - Keep the message under 72 characters.
                                                - Describe the actual change, not the implementation process.
                                                - Return only the commit message, without quotes or Markdown.
                                                - Do not invent changes that are not evident from the diff.

                                                Staged changes:
                                                {limited_diff}
                                            '''
                                    with console.status("[bold cyan]Generating commit message...[/bold cyan]", spinner="arc"):
                                        # pyrefly: ignore[not-async]
                                        response = await client.chat.completions.create(
                                            model=current_model,
                                            messages=[
                                                {
                                                    "role": "system",
                                                    "content": (
                                                        "You generate a concise Git commit messages with the Conventional Commits format. Return only the commit message text."
                                                    ),
                                                },
                                                {"role": "user", "content": prompt},
                                            ],
                                        )

                                    commit_message = (response.choices[0].message.content or "").strip().strip('"').strip("'")

                                    if not commit_message:
                                        result = "Failed to generate a commit message."
                                    else:
                                        console.print(f"\n[bold]Generated Commit Message:[/bold] {commit_message}")
                                        confirmed = await asyncio.to_thread(
                                            typer.confirm,
                                            "Do you want to commit with this message?",
                                            default=False,
                                        )
                                        if confirmed:
                                            result = await asyncio.to_thread(
                                                gitOperation,
                                                operation="commit",
                                                commit_message=commit_message,
                                            )
                                        else:
                                            result = "Commit cancelled. No commit was created."
                                            cancelled = True

                            else:
                                result = await asyncio.to_thread(
                                    gitOperation,
                                    operation=operation,
                                    file_name=arguments.get("file_name", "."),
                                )
                            console.print(f"[yellow]Git result:[/yellow] {result}")
                        elif tool_call.function.name == "executeTool":
                            command = arguments.get("command", "")
                            console.print(f"[cyan]Executing Command Tool:[/cyan] {command}")
                            result = await asyncio.to_thread(
                                executeTool,
                                command=command,
                                ask_confirm=True,
                            )
                            if "cancelled by user" in result.lower():
                                console.print("[yellow]Command execution was cancelled by the user.[/yellow]")
                                cancelled = True
                            elif result.startswith("Error") or result.startswith("Execution rejected") or "failed" in result.lower():
                                console.print("[red]Command finished with an error or rejection.[/red]")
                            else:
                                console.print("[green]Command executed successfully.[/green]")
                        else:
                            result = f"Unknown tool: {tool_call.function.name}"

                    except Exception as exc:
                        result = f"Tool execution failed: {exc}"
                        console.print(f"[bold red]Tool execution error:[/bold red] {exc}")

                    messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": str(result)})

                    if cancelled:
                        break

                if cancelled:
                    break

                status_text = "Processing response..."

            except Exception as exc:
                console.print(f"[bold red]Error:[/bold red] {exc}")
                break

@app.command()
def chat():
    """Start an interactive CodeIq chat with Git and File tools."""
    async def runner():
        try:
            await _chat()
        finally:
            # pyrefly: ignore[not-async]
            await client.close()
    asyncio.run(runner())

async def _generate_response(prompt: str):
    current_model = get_selected_model()
    typer.echo(f"\nQ: {prompt}")
    with console.status("[bold cyan]Thinking...[/bold cyan]", spinner="arc"):
        # pyrefly: ignore[not-async]
        response = await client.chat.completions.create(
            model=current_model,
            messages=[{"role": "user", "content": prompt}],
        )
    console.print(response.choices[0].message.content, style="green")

# Generate response from AI model
@app.command()
def generate_response(prompt: str):
    """
    Generates a response from the AI model based on the given prompt.
    Usage:
        python cli.py generate-response "What is the capital of France?"
    Args:
        prompt (str): The prompt to send to the AI model.
    """
    asyncio.run(_generate_response(prompt))

@app.command(name="models")
def models():
    """
    Select an AI model interactively using arrow keys (like npm create vite).
    Usage:
        codeiq models
    """
    current_model = get_selected_model()
    try:
        chosen = select_model_interactive(AVAILABLE_MODELS, default_option=current_model)
        set_selected_model(chosen)
        console.print(f"\n[bold green]✓[/bold green] Selected model: [bold cyan]{chosen}[/bold cyan]")
    except KeyboardInterrupt:
        console.print("\n[dim]Model selection cancelled.[/dim]")

if __name__ == "__main__":
    app()