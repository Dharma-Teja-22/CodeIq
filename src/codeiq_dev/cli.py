from asyncio import trsock
from codeiq_dev.utils import repoMap
from codeiq_dev.tools.git_tools import *
from codeiq_dev.tools.file_tools import fileOperation
from codeiq_dev.tools.miscellaneous_tools import executeTool
import asyncio
import sys
import os
from pathlib import Path
import typer
from rich.console import Console
from rich.text import Text
# from rich.markdown import Markdown
import json
from codeiq_dev.tools.registry import tools
import msvcrt

# Ensure standard output uses UTF-8 on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

app = typer.Typer()
console = Console()

from typing import Optional

from codeiq_dev.core.settings import *
from codeiq_dev.core.config import (
    add_model_to_config,
    get_available_models,
    get_selected_model,
    set_selected_model,
)
from codeiq_dev.core.llm import (
    close_client,
    create_chat_stream,
    generate_commit_message,
    stream_chat_turn,
)


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

# Async chat implementation
async def _chat():
    """Interactive CodeIq chat with Git and File tools using asyncio."""
    session_tokens = 0

    while True:
        prompt = await asyncio.to_thread(
            typer.prompt,
            typer.style("User", fg=typer.colors.CYAN, bold=True),
        )

        if prompt.strip().lower() in ("exit", "quit","bye","close"):
            console.print("[yellow]Chat ended.[/yellow]")
            break

        repo_structure = repoMap.get_all_paths()

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
                    f"Here is the project structure: {repo_structure}, if there is any folder which might be related to the request, please explore it and provide the response."
                ),
            },
            {"role": "user", "content": prompt},
        ]

        query_tokens = 0
        completion_tokens = 0

        status_text = "Thinking..."
        current_model = get_selected_model()
        console.print(Text("Assistant:", style="bold cyan"))
        # Inner loop handles all tool-calling rounds for this question.
        while True:
            requested_tool_calls = []
            try:
                with console.status(
                    f"[bold cyan]{status_text}[/bold cyan]",
                    spinner="arc",
                ) as status_spinner:
                    def handle_token(tok: str):
                        if status_spinner and status_spinner._live.is_started:
                            status_spinner.stop()
                        console.print(tok, style="green", end="")

                    assistant_message, usage_info = await stream_chat_turn(
                        messages=messages,
                        model=current_model,
                        with_tools=True,
                        on_token=handle_token,
                    )

                    requested_tool_calls = assistant_message.tool_calls
                    full_content = assistant_message.content

                    if usage_info["query_tokens"]:
                        query_tokens = usage_info["query_tokens"]
                    if usage_info["completion_tokens"]:
                        completion_tokens = usage_info["completion_tokens"]
                    if usage_info["session_tokens"]:
                        session_tokens = usage_info["session_tokens"]

                if assistant_message.content:
                    console.print()

                # No more tool calls: display tokens and end round.
                if not requested_tool_calls:
                    if (not full_content.strip()) and status_text != "Thinking...":
                        console.print(Text("Assistant:", style="bold cyan"), Text("Done.", style="green"))
                    console.print(f"[dim]Tokens: Query: {query_tokens} | Completion: {completion_tokens} | Session: {session_tokens}[/dim]\n")
                    break
                
                # Validate that all requested tools exist in the tools registry
                invalid_tool_names = [
                    tc.function.name
                    for tc in requested_tool_calls
                    if getattr(tc, "function", None) and tc.function.name not in tools
                ]
                if invalid_tool_names:
                    console.print(f"[yellow]Warning: Hallucinated non-existent tool: {', '.join(invalid_tool_names)}. Re-generating the tool call again ... [/yellow]")
                    messages.append(assistant_message.model_dump(exclude_none=True))
                    for tc in requested_tool_calls:
                        name = getattr(tc,"function", None) and tc.function.name
                        if name not in tools:
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tc.id,
                                "content": (
                                    f"Error: Tool '{name}' does not exist. "
                                    f"Available tools are: {list(tools.keys())}. "
                                    "Please call only from the available tools."
                                ),
                            })
                    status_text = "Retrying tool call..."
                    continue
                            
                # Preserve the assistant's tool-call message.
                messages.append(assistant_message.model_dump(exclude_none=True))

                cancelled = False

                # Execute all tool calls returned in this response.
                for tool_call in requested_tool_calls:
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
                                    with console.status("[bold cyan]Generating commit message...[/bold cyan]", spinner="arc"):
                                        commit_message = await generate_commit_message(diff, model=current_model)

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
            await close_client()
    asyncio.run(runner())

async def _generate_response(prompt: str):
    current_model = get_selected_model()
    typer.echo(f"\nQ: {prompt}")

    p_tokens = 0
    c_tokens = 0
    t_tokens = 0

    with console.status("[bold cyan]Thinking...[/bold cyan]", spinner="arc") as status_spinner:
        # pyrefly: ignore[not-async]
        stream_response = await create_chat_stream(
            messages=[{"role": "user", "content": prompt}],
            model=current_model,
            with_tools=False,
        )

        printed_prefix = False
        async for chunk in stream_response:
            if getattr(chunk, "usage", None) and chunk.usage:
                p_tokens = chunk.usage.prompt_tokens or p_tokens
                c_tokens = chunk.usage.completion_tokens or c_tokens
                t_tokens = chunk.usage.total_tokens or (p_tokens + c_tokens)

            if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                if status_spinner:
                    status_spinner.stop()
                console.print(chunk.choices[0].delta.content, style="green", end="")
                printed_prefix = True

    if printed_prefix:
        console.print()

    console.print(f"[dim]Tokens: Query: {p_tokens} | Completion: {c_tokens} | Total: {t_tokens}[/dim]\n")

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
def models(
    add: Optional[str] = typer.Option(
        None,
        "--add",
        "-a",
        help="Add a new model to the Gemini provider configuration.",
    ),
):
    """
    Select an AI model interactively or add a new model for the Gemini provider.
    Usage:
        codeiq models
        codeiq models --add <modelName>
    """
    if add:
        model_name = add.strip().strip("'").strip('"')
        if not model_name:
            console.print("[bold red]Error:[/bold red] Model name cannot be empty.")
            return

        added = add_model_to_config(model_name, provider="gemini")
        if added:
            console.print(f"[bold green]✓ Added model '{model_name}' under Gemini provider in JSON.[/bold green]")
        else:
            console.print(f"[dim]Model '{model_name}' already exists under Gemini provider.[/dim]")
        return

    available_models = get_available_models(provider="gemini")
    current_model = get_selected_model(provider="gemini")
    try:
        chosen = select_model_interactive(available_models, default_option=current_model)
        set_selected_model(chosen, provider="gemini")
        console.print(f"\n[bold green]✓[/bold green] Selected model: [bold cyan]{chosen}[/bold cyan]")
    except KeyboardInterrupt:
        console.print("\n[dim]Model selection cancelled.[/dim]")

if __name__ == "__main__":
    app()