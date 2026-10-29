from openai.types.beta import beta_computer_action_list
from codeiq_dev.tools.git_tools import *
from codeiq_dev.tools.file_tools import findFile, readFile
from openai import OpenAI
from dotenv import load_dotenv
from pathlib import Path
from typing import Optional
import os
import typer
from rich.console import Console
from rich.text import Text
import json

load_dotenv()
app = typer.Typer()
console = Console()

client = OpenAI(
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
    }
]

# Generate response from AI model in a chat mode - Loop
@app.command()
def chat():
    """Start an interactive CodeIq chat with Git tools."""
    while True:
        prompt = typer.prompt(
            typer.style("User", fg=typer.colors.CYAN, bold=True)
        )

        if prompt.strip().lower() in ("exit", "quit"):
            console.print("[yellow]Chat ended.[/yellow]")
            break

        messages = [
            {
                "role": "system",
                "content": (
                    "You are CodeIq, an AI coding assistant that performs Git operations. Always choose the correct operation based on the user's request. Use add to stage new, modified, or deleted files, and use commit to save staged changes with a commit message. If the user asks to commit the latest added or staged files, select commit instead of add. If the user asks to add files and then commit them, perform add first and commit next. Use push to upload committed changes, pull to get the latest remote changes, and branch to show the current branch name. Never confuse these operations or claim success unless the tool result confirms it. Note: We do have multiple tool calls too. So if you need to perform multiple operations, call the tool for each operation sequentially. Example: If user asks to add and commit, call add tool first and then commit tool. After a tool has executed and returned a result, always provide a concise summary or confirmation to the user."
                ),
            },
            {"role": "user", "content": prompt},
        ]

        status_text = "Thinking..."
        # Inner loop handles all tool-calling rounds for this question.
        while True:
            try:
                with console.status(
                    f"[bold cyan]{status_text}[/bold cyan]",
                    spinner="arc",
                ):
                    response = client.chat.completions.create(
                        model="gemini-3.5-flash-lite",
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

                # Execute all tool calls returned in this response.
                for tool_call in assistant_message.tool_calls:
                    try:
                        if tool_call.function.name != "gitOperations":
                            result = (f"Unknown tool: {tool_call.function.name}")
                        else:
                            arguments = json.loads(tool_call.function.arguments)
                            operation = arguments["operation"]
                            console.print(f"[cyan]Executing Git operation: {operation}[/cyan]")

                            if operation.lower() == "commit":
                                diff = gitDiff()
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
                                    with console.status("[bold cyan]Generating commit message...[/bold cyan]",spinner="arc",):
                                        response = client.chat.completions.create(
                                            model="gemini-3.5-flash-lite",
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
                                        if typer.confirm("Do you want to commit with this message?",default=False,):
                                            result = gitOperation(operation="commit",commit_message=commit_message,
                                            )
                                        else:
                                            result = "Commit cancelled. No commit was created."

                            else:
                                result = gitOperation(operation=operation,file_name=arguments.get("file_name", "."),)

                    except Exception as exc:
                        result = f"Tool execution failed: {exc}"

                    console.print(f"[yellow]Git result:[/yellow] {result}")
                    messages.append({"role": "tool","tool_call_id": tool_call.id,"content": str(result),})

                status_text = "Processing response..."

            except Exception as exc:
                console.print(f"[bold red]Error:[/bold red] {exc}")
                break

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
    typer.echo(f"\nQ: {prompt}")
    
    with console.status("[bold cyan]Thinking...[/bold cyan]", spinner="arc"):
        response = client.chat.completions.create(
            model="gemini-3.5-flash-lite",
            messages=[{"role": "user", "content": prompt}],
        )

    console.print(response.choices[0].message.content, style="green")

# Find file dynamically without extension
@app.command(name="find-file")
def find_file_cmd(filename: Optional[str] = typer.Argument(None,help="Name of the file to search for. Prompted if not provided."),
    directory: Optional[str] = typer.Option(None,"--directory","-d",help="Target directory to search. Defaults to current working directory where the command is executed.")):
    """
    Search recursively for a file by name matching any extension in the current directory.
    """
    target_dir = Path(directory).resolve() if directory else Path.cwd()
    file_name = filename if filename else typer.prompt("Enter file name (without extension)").strip()
    if not file_name:
        console.print("[bold red]Error:[/bold red] File name cannot be empty.")
        raise typer.Exit(code=1)

    matches = findFile(target_directory=target_dir, filename=file_name)
    if matches:
        console.print(f"[bold green]Found {len(matches)} match(es):[/bold green]")
        for file in matches:
            console.print(f" - {file.resolve()}")
    else:
        console.print("[yellow]No matching files found.[/yellow]")

# Read file content using findFile
@app.command(name="read-file")
def read_file_cmd(
    filename: Optional[str] = typer.Argument(None, help="Name of the file to read (without extension). Prompted if not provided."),
    directory: Optional[str] = typer.Option(None, "--directory", "-d", help="Target directory to search. Defaults to current working directory.")
):
    """
    Find a file by name and display its content.
    """
    target_dir = Path(directory).resolve() if directory else Path.cwd()
    file_name = filename if filename else typer.prompt("Enter file name (without extension)").strip()
    if not file_name:
        console.print("[bold red]Error:[/bold red] File name cannot be empty.")
        raise typer.Exit(code=1)

    content = readFile(filename=file_name, target_directory=target_dir)
    console.print(content)

if __name__ == "__main__":
    app()
