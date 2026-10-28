from codeiq_dev.tools.git_tools import *
from openai import OpenAI
from dotenv import load_dotenv
import os
import typer
from rich.console import Console
import subprocess
from rich.text import Text

load_dotenv()
app = typer.Typer()
console = Console()

client = OpenAI(
    api_key=os.getenv("GEMINI_API_KEY"),
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
)

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

# Generate response from AI model in a chat mode - Loop
@app.command()
def chat():
    """
    Generates a response from the AI model based on the given prompt.
    Usage:
        codeiq chat
    Args:
        prompt (str): The prompt to send to the AI model.
    Format:
        User: <Question>
        Assistant: <Response from AI>
        ...
    """
    while True:
        prompt_text = typer.style("User", fg=typer.colors.CYAN, bold=True)
        prompt = typer.prompt(prompt_text)
        if prompt.lower() in ('exit','quit'):
            break
        with console.status("[bold cyan]Thinking...[/bold cyan]", spinner="arc"):
            response = client.chat.completions.create(
                model="gemini-3.5-flash-lite",
                messages=[{"role": "user", "content": prompt}],
        )
        assistant = Text("Assistant:", style="bold cyan")
        message = Text(response.choices[0].message.content, style="green")
        console.print(assistant, message)

# Git Commands
@app.command()
def add(file_name: str = typer.Argument('.', help='File name or "." for all files')):
    """
    Generates "git add ." command 
    """
    with console.status("[bold cyan]Adding files...[/bold cyan]", spinner="arc"):
        result = gitAdd(file_name)
        console.print(result, style="green")

@app.command()
def commit():
    """
    Generates a commit message from staged Git changes.
    Usage:
        python cli.py commit
    """
    result = subprocess.run(["git", "diff", "--cached"],capture_output=True,text=True,encoding="utf-8",errors="replace")
    if result.returncode != 0:
        typer.echo(f"Failed to get the diff: {result.stderr}")
        raise typer.Exit(code=1)

    diff = result.stdout or ""

    if not diff.strip():
        typer.echo("No staged changes found.")
        raise typer.Exit(code=0)

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
    with console.status("[bold cyan] Generating commit message ...[/bold cyan]",spinner="arc"):
        response = client.chat.completions.create(
            model="gemini-3.5-flash-lite",
            messages=[
                {"role": "system","content": "You generate a concise Git commit messages with the Conventional Commits format. Return only the commit message text."},   
                {"role": "user","content": prompt}
            ],
        )

    commit_message = (response.choices[0].message.content or "").strip().strip('"').strip("'")

    if not commit_message:
        typer.echo("Failed to generate a commit message.")
        raise typer.Exit(code=1)

    console.print(f"Generated Commit Message: {commit_message}",style="green")

    # Ask user to confirm the commit message
    confirm = typer.confirm("Do you want to commit with this message?")

    if confirm:
        with console.status("[bold cyan]Committing changes...[/bold cyan]",spinner="arc"):
            gitCommit(commit_message)
    else:
        typer.echo("Commit cancelled.")

@app.command()
def git(type: str = typer.Option(..., "--type", help="Git operation: add, push, pull, branch"),file_name: str = typer.Option(".", "--file-name")):
    if type.lower() not in ["add", "push", "pull", "branch"]:
        typer.echo("Invalid Git operation type. Use: add, push, pull, branch")
        raise typer.Exit(code=1)
    with console.status(f"[bold cyan]Performing Git {type}...[/bold cyan]",spinner="arc"):
        result = gitOperation(type.lower(),file_name)
        console.print(result, style="green")

if __name__ == "__main__":
    app()
