from datetime import datetime
from codeiq_dev.utils import repoMap
from codeiq_dev.tools.git_tools import *
from codeiq_dev.tools.file_tools import fileOperation
from codeiq_dev.tools.miscellaneous_tools import executeTool
from codeiq_dev.tools.web_search_tool import DDGSearch, read_url

import asyncio
import sys
import os
from pathlib import Path
import typer
from rich.console import Console
from rich.text import Text
from rich.markdown import Markdown
from rich.live import Live
import json
from codeiq_dev.tools.registry import tools, tool_schema
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
from codeiq_dev.core.config import load_config, save_config
from codeiq_dev.core.llm import (
    close_client,
    create_chat_stream,
    generate_commit_message,
    generate_session_title,
    stream_chat_turn,
)
from codeiq_dev.core.compaction import maybe_compact_session
from codeiq_dev.core.session import (
    SESSIONS_DIR,
    append_message,
    close_session,
    create_session,
    find_session_file,
    get_session_file_path,
    list_sessions,
    load_session,
    purge_deleted_sessions,
    restore_session,
    save_session,
    set_model,
    soft_delete_session,
    update_session_title,
    update_tokens,
)

# Allows navigating using UP/DOWN arrow keys and selecting with ENTER -  For models
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
async def _chat(session_id: Optional[str] = None):
    """Interactive CodeIq chat with Git and File tools using asyncio."""
    is_new_session = session_id is None
    if session_id:
        session = load_session(session_id)
    else:
        session = create_session(save=False)


    current_model = settings.MODEL
    session["model_name"] = current_model

    if not is_new_session:
        set_model(session, current_model)
        session_file_path = get_session_file_path(session["session_id"])
        console.print(f"[dim]Session: {session['session_id']} | Path: {session_file_path}[/dim]")
    
    repo_structure = repoMap.get_all_paths()
    file_repo_url = str(Path.cwd())

    # Build repo context including repository URL and directory structure
    repo_context_parts = [f"Project Structure: {repo_structure}"]
    if file_repo_url:
        repo_context_parts.append(f"Repository URL: {file_repo_url}")
    repo_context_str = " | ".join(repo_context_parts)

    system_prompt = (
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
        f"Here is the project structure and repository info: {repo_context_str}, if there is any folder which might be related to the request, please explore it and provide the response."
        "For Web Research and URL Content Extraction:"
        "STRICT RULE: Always prioritize the LLM's built-in knowledge and reasoning. Invoke web search tools only when the LLM cannot confidently answer or when external research, up-to-date information, or fact-checking is required. Avoid unnecessary web searches for basic definitions, general knowledge, and programming concepts (e.g., What is Python?, Define ADK,...)."
        "1. Web Search (webSearch): Use this tool when the user asks to research a topic, library, framework, latest documentation, or find solutions online. Formulate focused search queries. Use the top results to understand the subject or When the user asks to research a topic, use webSearch to retrieve information. Once relevant search results are obtained, synthesize and provide a clear, comprehensive, and complete summary directly to the user in clean Markdown. Do not end your response abruptly or stop mid-sentence."
        "2. Direct Webpage Reading (fetchWebpageMarkdown): When the user provides a specific URL (or when a webSearch result points to an authoritative documentation/article URL that needs deep reading), invoke fetchWebpageMarkdown to extract its full clean markdown content via Jina AI Reader. "
        "3. Synthesis & Complete Delivery: Never stop after executing search or URL fetching. Once tool results are returned, immediately synthesize the retrieved facts into a thorough, well-structured, and complete response with headings, bullet points, code snippets (if applicable), and references. Always complete your full explanation without cutting off or leaving the summary incomplete."
        "**NOTE**: Ensure that all responses are well-structured, clearly defined, and formatted exclusively in Markdown."
    )

    # Initialize messages list with system prompt and any resumed session messages
    saved_msgs = [m for m in session.get("messages", []) if m.get("role") != "system"]
    messages = [{"role": "system", "content": system_prompt}] + saved_msgs

    if saved_msgs:
        console.print(f"[green]Resumed session with {len(saved_msgs)} previous messages.[/green]\n")

    session_tokens = session.get("token_usage", {}).get("session_tokens", 0)

    while True:
        prompt = await asyncio.to_thread(
            typer.prompt,
            typer.style("User", fg=typer.colors.CYAN, bold=True),
        )

        clean_prompt = prompt.strip().lower()
        if clean_prompt in ("exit", "quit", "bye", "close"):
            console.print("[yellow]Exited chat.[/yellow]")
            break
        elif clean_prompt in ("close session", "end session"):
            close_session(session["session_id"])
            console.print(f"[bold yellow]Session '{session['session_id']}' marked as closed.[/bold yellow]")
            break
        elif clean_prompt in ("delete", "delete session", "drop session"):
            soft_delete_session(session["session_id"])
            console.print(f"[bold red]Session '{session['session_id']}' soft-deleted.[/bold red]")
            break
        
        # Append user prompt to messages and session JSON
        user_message = {"role": "user", "content": prompt}
        messages.append(user_message)
        # append_message(session, user_message)

        if is_new_session:
            try:
                ai_title = await generate_session_title(prompt, model=current_model)
                # new_session_id = update_session_title(session, ai_title)
                # console.print(f"[dim]Session Title: {ai_title} | ID: {new_session_id}[/dim]")
            except Exception:
                ai_title="New Session"
            clean_title = "".join(c for c in ai_title if c.isalnum() or c in (" ", "-", "_")).strip()
            if not clean_title:
                clean_title='session'
            project_name = session.get("project_name")
            session["title"] = ai_title
            session["session_id"] = f"{project_name}-{clean_title}"
            
            # Append user message in-memory without saving yet
            session.setdefault("messages", []).append(user_message)
            session["updated_at"] = datetime.now().isoformat()
            
            # Now create and persist the session file for the first time
            save_session(session)
            
            session_file_path = get_session_file_path(session["session_id"])
            console.print(f"[dim]Session Title: {ai_title} | Path: {session_file_path}[/dim]")
            is_new_session = False
        else:
            # Resumed/existing session: append and save directly
            append_message(session, user_message)
        
        # Check compaction on new input user message before LLM inference
        try:
            compacted = await maybe_compact_session(
                session,
                current_context_tokens=None,
                system_prompt=system_prompt,
                tools=tool_schema,
                file_repo_url=file_repo_url,
            )
            if compacted:
                messages = [
                    {"role": "system", "content": system_prompt}
                ] + [m for m in session.get("messages", []) if m.get("role") != "system"]
                console.print("[dim]⚡ Conversation context compacted below token threshold.[/dim]")
        except Exception:
            pass
        
        # If session has default/initial title, generate AI title and rename file to <projectName>-<title>
        # if session.get("title") in ("New Session", "Untitled Session", None):

        query_tokens = 0
        completion_tokens = 0
        final_response = ""
        
        status_text = "Thinking..."
        current_model = settings.MODEL
        set_model(session, current_model)
        console.print(Text("Assistant:", style="bold cyan"))
        # Inner loop handles all tool-calling rounds for this question.
        while True:
            requested_tool_calls = []
            try:
                with console.status(
                    f"[bold cyan]{status_text}[/bold cyan]",
                    spinner="arc",
                ) as status_spinner:
                    live: Optional[Live] = None
                    def handle_token(tok: str):
                        nonlocal final_response, live
                        if not tok:
                            return
                        # Stop thinking spinner before streaming text
                        if status_spinner and status_spinner._live.is_started:
                            status_spinner.stop()
                        final_response += tok
                        # Start Live display once on first token
                        if live is None:
                            live = Live(Markdown(final_response), console=console, refresh_per_second=10)
                            live.start()
                        else:
                            live.update(Markdown(final_response))

                    assistant_message, usage_info = await stream_chat_turn(
                        messages=messages,
                        model=current_model,
                        with_tools=True,
                        on_token=handle_token,
                    )
                    if live is not None:
                        live.stop()

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
                    # Accumulate session tokens
                    accum_prompt = session.get("session_prompt_tokens", 0) + query_tokens
                    accum_comp = session.get("session_completion_tokens", 0) + completion_tokens
                    accum_total = session.get("total_tokens", 0) + (query_tokens + completion_tokens)

                    if (not full_content.strip()) and status_text != "Thinking...":
                        console.print(Text("Assistant:", style="bold cyan"), Text("Done.", style="green"))
                    console.print(f"[dim]Turn Tokens: Query: {query_tokens} | Completion: {completion_tokens} | Session Total: {accum_total}[/dim]\n")
                    # Save assistant message to session JSON
                    asst_dump = assistant_message.model_dump(exclude_none=True)
                    messages.append(asst_dump)
                    append_message(session, asst_dump)
                    update_tokens(
                        session,
                        prompt_tokens=accum_prompt,
                        completion_tokens=accum_comp,
                        total_tokens=accum_total,
                        increment_requests=True,
                    )

                    try:
                        # Measure total tokens (input messages + assistant output + tool calls)
                        compacted = await maybe_compact_session(
                            session,
                            current_context_tokens=None,
                            system_prompt=system_prompt,
                            tools=tool_schema,
                            file_repo_url=file_repo_url,
                        )
                        if compacted:
                            messages = [
                                {"role": "system", "content": system_prompt}
                            ] + [m for m in session.get("messages", []) if m.get("role") != "system"]
                            console.print("[dim]⚡ Conversation context compacted below token threshold.[/dim]")
                    except Exception as comp_err:
                        pass

                    break
                
                # Validate that all requested tools exist in the tools registry
                invalid_tool_names = [
                    tc.function.name
                    for tc in requested_tool_calls
                    if getattr(tc, "function", None) and tc.function.name not in tools
                ]
                if invalid_tool_names:
                    console.print(f"[yellow]Warning: Hallucinated non-existent tool: {', '.join(invalid_tool_names)}. Re-generating the tool call again ... [/yellow]")
                    asst_dump = assistant_message.model_dump(exclude_none=True)
                    messages.append(asst_dump)
                    append_message(session, asst_dump)
                    for tc in requested_tool_calls:
                        name = getattr(tc,"function", None) and tc.function.name
                        if name not in tools:
                            err_msg = {
                                "role": "tool",
                                "tool_call_id": tc.id,
                                "content": (
                                    f"Error: Tool '{name}' does not exist. "
                                    f"Available tools are: {list(tools.keys())}. "
                                    "Please call only from the available tools."
                                ),
                            }
                            messages.append(err_msg)
                            append_message(session, err_msg)
                    status_text = "Retrying tool call..."
                    continue
                            
                # Preserve the assistant's tool-call message.
                asst_dump = assistant_message.model_dump(exclude_none=True)
                messages.append(asst_dump)
                append_message(session, asst_dump)

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
                        elif tool_call.function.name == "webSearch":
                            query = arguments.get("query", "")
                            console.print(f"[cyan]Searching the web for:[/cyan] {query}")
                            search_results = await asyncio.to_thread(DDGSearch, query=query)
                            result = json.dumps(search_results, indent=2)
                            console.print(f"[green]Retrieved {len(search_results)} search results.[/green]")
                        elif tool_call.function.name == "fetchWebpageMarkdown":
                            target_url = arguments.get("url", "")
                            console.print(f"[cyan]Fetching webpage markdown from:[/cyan] {target_url}")
                            result = await asyncio.to_thread(read_url, target_url=target_url)
                            console.print(f"[green]Successfully loaded content from '{target_url}'.[/green]")
                        else:
                            result = f"Unknown tool: {tool_call.function.name}"

                    except Exception as exc:
                        result = f"Tool execution failed: {exc}"
                        console.print(f"[bold red]Tool execution error:[/bold red] {exc}")

                    tool_resp = {"role": "tool", "tool_call_id": tool_call.id, "content": str(result)}
                    messages.append(tool_resp)
                    append_message(session, tool_resp)

                    # Check compaction after tool execution results are appended
                    try:
                        compacted = await maybe_compact_session(session, current_context_tokens=None)
                        if compacted:
                            messages = [
                                {"role": "system", "content": system_prompt}
                            ] + [m for m in session.get("messages", []) if m.get("role") != "system"]
                            console.print("[dim]⚡ Conversation context compacted below token threshold.[/dim]")
                    except Exception:
                        pass

                    if cancelled:
                        break

                if cancelled:
                    break

                status_text = "Processing response..."

            except Exception as exc:
                # Display the exact underlying error message (e.g. 429 Rate Limit / Quota Exceeded)
                # when tenacity retries are exhausted or other exceptions occur.
                console.print(f"[bold red]Error:[/bold red] {exc}")
                break

# Chat Loop
@app.command()
def chat(
    session: Optional[str] = typer.Option(
        None, "--session", "-s", help="Resume a specific session by ID or prefix"
    ),
    resume: bool = typer.Option(
        False, "--resume", "-r", help="Resume the most recent session"
    ),
):
    """
    Start an interactive CodeIq chat session.
    
    Usage:
        codeiq chat                      # Starts a new session
        codeiq chat --resume / -r        # Continues your latest session
        codeiq chat --session <id> / -s  # Resumes a specific session
    """
    target_session_id = session

    if resume and not target_session_id:
        existing = list_sessions()
        if existing:
            target_session_id = existing[0]["session_id"]
            console.print(f"[bold cyan]Resuming latest session:[/bold cyan] {target_session_id}")
        else:
            console.print("[yellow]No existing sessions found. Starting a new one.[/yellow]")
    elif target_session_id:
        session_file = find_session_file(target_session_id)
        if session_file:
            target_session_id = session_file.stem
            console.print(f"[bold cyan]Resuming session:[/bold cyan] {target_session_id}")
        else:
            console.print(f"[bold red]Error:[/bold red] Session '{target_session_id}' not found. Starting a new one.")
            target_session_id = None

    async def runner():
        try:
            await _chat(session_id=target_session_id)
        finally:
            # pyrefly: ignore[not-async]
            await close_client()
    asyncio.run(runner())

# Command to work with sessions (get list of sessions | soft delete | resume | direct delete | ... )
@app.command(name="sessions")
def sessions(
    close: Optional[str] = typer.Option(
        None, "--close", "-c", help="Close a specific session by ID or prefix"
    ),
    delete: Optional[str] = typer.Option(
        None, "--delete", "-d", help="Soft delete a session (it will no longer be listed or resumeable)"
    ),
    restore: Optional[str] = typer.Option(
        None, "--restore", help="Restore a soft-deleted session by ID or prefix"
    ),
    purge: Optional[str] = typer.Option(
        None,
        "--purge",
        help="Permanently delete a soft-deleted session by ID or prefix. Use '--purge all' to delete all soft-deleted sessions.",
    ),
    show_deleted: bool = typer.Option(
        False, "--show-deleted", help="Include soft-deleted sessions in the list"
    ),
):
    """
    List, close, soft-delete, or permanently purge chat sessions in C:\\Users\\<user>\\.codeiq\\sessions.
    
    Usage:
        codeiq sessions               # List session IDs with status
        codeiq sessions --close <id>  # Mark a session as closed
        codeiq sessions --delete <id> # Soft delete a session
        codeiq sessions --purge <id>  # Permanently remove a soft-deleted session
        codeiq sessions --purge all   # Permanently remove all soft-deleted sessions
        codeiq sessions --restore <id># Restore a soft-deleted session
    """
    # 1. Permanent purge of soft-deleted session(s)
    if purge:
        if purge.strip().lower() == "all":
            purged = purge_deleted_sessions()
            if purged:
                console.print(f"[bold green]✓ Permanently removed {len(purged)} soft-deleted session(s):[/bold green]")
                for pid in purged:
                    console.print(f"  - {pid}")
            else:
                console.print("[yellow]No soft-deleted sessions found to purge.[/yellow]")
            return
        else:
            purged = purge_deleted_sessions(session_id=purge)
            if purged:
                console.print(f"[bold green]✓ Permanently removed session: {purged[0]}[/bold green]")
            else:
                console.print(f"[bold red]Error:[/bold red] Soft-deleted session '{purge}' not found.")
            return

    # 2. Soft delete
    if delete:
        res = soft_delete_session(delete)
        if not res:
            console.print(f"[bold red]Error:[/bold red] Session '{delete}' not found in {SESSIONS_DIR}")
            return
        console.print(f"[bold green]✓ Session '{res}' has been soft-deleted.[/bold green]")
        console.print("[dim]It will no longer appear in 'codeiq sessions' or be opened via '--resume'/'--session'.[/dim]")
        return

    # 3. Restore soft-deleted
    if restore:
        res = restore_session(restore)
        if not res:
            console.print(f"[bold red]Error:[/bold red] Session '{restore}' not found in {SESSIONS_DIR}")
            return
        console.print(f"[bold green]✓ Session '{res}' has been restored.[/bold green]")
        return

    # 4. Close session
    if close:
        res = close_session(close)
        if not res:
            console.print(f"[bold red]Error:[/bold red] Session '{close}' not found in {SESSIONS_DIR}")
            return
        console.print(f"[bold green]✓ Session '{res}' is now closed.[/bold green]")
        return

    # 5. List sessions - render clean session ID and status (no table data)
    session_list = list_sessions(include_deleted=show_deleted)
    if not session_list:
        console.print(f"[yellow]No saved sessions found[/yellow]")
        return

    console.print(f"[bold cyan]Sessions ({SESSIONS_DIR}):[/bold cyan]\n")
    for s in session_list:
        if s.get("is_deleted"):
            status_text = "[bold red][deleted][/bold red]"
        elif s.get("status") == "closed":
            status_text = "[bold yellow][closed][/bold yellow]"
        else:
            status_text = "[bold green][active][/bold green]"

        console.print(f"• [cyan]{s['session_id']}[/cyan] {status_text}")

    console.print(
        "\n[dim]Resume: [bold cyan]codeiq chat -s <id>[/bold cyan] | Purge all deleted: [bold cyan]codeiq sessions --purge all[/bold cyan][/dim]"
    )

async def _generate_response(prompt: str) -> None:
    """
    Stream and print a one-off AI completion response for a given prompt without tool calling.

    Args:
        prompt (str): The user query or instruction sent to the AI model.

    Returns:
        None: Streams tokens directly to standard console output and prints token usage.
    """
    current_model = settings.MODEL
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

# For adding and changing the models
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
        try:
            config = load_config()
            provider_data = config.setdefault("providers", {}).setdefault("gemini", {})
            models_list = provider_data.setdefault("models", [])
            if model_name in models_list:
                added = False
            else:
                models_list.append(model_name)
                save_config(config)
                added = True
        except Exception:
            added = False
        if added:
            console.print(f"[bold green]✓ Added model '{model_name}' under Gemini provider in JSON.[/bold green]")
        else:
            console.print(f"[dim]Model '{model_name}' already exists under Gemini provider.[/dim]")
        return

    try:
        config = load_config()
        models = config.get("providers", {}).get("gemini", {}).get("models", [])
        available_models = list(models) if isinstance(models, list) else []
    except Exception:
        available_models = []
    current_model = settings.MODEL
    try:
        chosen = select_model_interactive(available_models, default_option=current_model)
        try:
            config = load_config()
            config["default_model"] = chosen
            config.pop("model", None)
            save_config(config)
        except Exception as e:
            console.print(f"[bold red]Error setting selected model: {e}[/bold red]")
        console.print(f"\n[bold green]✓[/bold green] Selected model: [bold cyan]{chosen}[/bold cyan]")
    except KeyboardInterrupt:
        console.print("\n[dim]Model selection cancelled.[/dim]")

if __name__ == "__main__":
    app()