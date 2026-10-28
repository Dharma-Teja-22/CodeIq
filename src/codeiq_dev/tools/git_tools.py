from dotenv import load_dotenv
from openai import OpenAI
import subprocess
import os

load_dotenv()

client = OpenAI(
    api_key=os.getenv("GEMINI_API_KEY"),
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
)

def gitAdd(file_name: str = ".") -> str:
    """Stage new, modified, and deleted files."""
    if file_name == ".":
        result = subprocess.run(
            ["git", "add", "-A"],
            capture_output=True,
            text=True,
        )
    else:
        result = subprocess.run(
            ["git", "add", "--", file_name],
            capture_output=True,
            text=True,
        )

    if result.returncode == 0:
        return f"Successfully staged changes: {file_name}"

    return f"Failed to stage changes: {result.stderr.strip()}"

def gitDiff():
    '''Get the diff of the staged changes'''
    result = subprocess.run(["git", "diff", "--cached"], capture_output=True, text=True)
    if result.returncode == 0:
        return result.stdout.strip()
    else:
        return f"Failed to get the diff"

def gitCommit(message: str):
    """Commit staged changes using the provided message."""
    result = subprocess.run(
        ["git", "commit", "-m", message],
        capture_output=True,
        text=True,
    )

    if result.returncode == 0:
        return f"Commit successful: {message}"

    return f"Commit failed: {result.stderr.strip()}"

def gitPush(branch_name: str):
    '''Push to a branch'''
    result = subprocess.run(["git", "push", "origin", branch_name], capture_output=True, text=True)
    if result.returncode == 0:
        return f"Pushed to branch: {branch_name}"
    else:
        return f"Failed to push to branch"

def gitPull(branch_name: str):
    '''Pull from a branch'''
    result = subprocess.run(["git", "pull", "origin", branch_name], capture_output=True, text=True)
    if result.returncode == 0:
        return f"Pulled from branch: {branch_name}"
    else:
        return f"Failed to pull from branch"

def getBranch():
    '''Get Current Branch Name'''
    result = subprocess.run(["git", "branch", "--show-current"], capture_output=True, text=True)
    if result.returncode == 0:
        return result.stdout.strip()
    else:
        return f"Failed to get branch name"

# def commit():
#     """
#     Generates a commit message from staged Git changes.
#     Usage:
#         python cli.py commit
#     """
#     result = subprocess.run(["git", "diff", "--cached"],capture_output=True,text=True,encoding="utf-8",errors="replace")
#     if result.returncode != 0:
#         return f"Failed to get the diff: {result.stderr}"
#     diff = result.stdout or ""
#     if not diff.strip():
#         return "No staged changes found."

#     # Pick the first 200 lines from the diff
#     diff_lines = diff.splitlines()
#     limited_diff = "\n".join(diff_lines[:200])

    # prompt = f'''Generate a short, descriptive Git commit message based on the staged changes. Follow Conventional Commits format.
    #              Use one of these prefixes:
    #                 - feat: for new functionality
    #                 - fix: for bug fixes
    #                 - refactor: for code restructuring
    #                 - docs: for documentation changes
    #                 - test: for test changes
    #                 - perf: for performance improvements
    #                 - chore: for maintenance tasks
    #                 - style: for formatting changes

    #                 Rules:
    #                 - Use simple, clear English.
    #                 - Start with the appropriate prefix.
    #                 - Use lowercase after the prefix.
    #                 - Keep the message under 72 characters.
    #                 - Describe the actual change, not the implementation process.
    #                 - Return only the commit message, without quotes or Markdown.
    #                 - Do not invent changes that are not evident from the diff.

    #                 Staged changes:
    #                 {limited_diff}
    #             '''
#     response = client.chat.completions.create(
#         model="gemini-3.5-flash-lite",
#         messages=[
#             {"role": "system","content": "You generate a concise Git commit messages with the Conventional Commits format. Return only the commit message text."},   
#             {"role": "user","content": prompt}
#             ],
#         )

#     commit_message = (response.choices[0].message.content or "").strip().strip('"').strip("'")

#     if not commit_message:
#         return "Failed to generate a commit message."

#     # Ask user to confirm the commit message
#     return f"Generated Commit Message: {commit_message}\n Do you want to commit with this message?"

# pyrefly: ignore[parse-error]
def gitOperation(operation: str, file_name: str = ".", commit_message: str = ""):
    if operation == "add":
        return gitAdd(file_name)
    
    if operation == "commit":
        return gitCommit(commit_message)

    elif operation == "push":
        branch_name = getBranch()
        return gitPush(branch_name)

    elif operation == "pull":
        branch_name = getBranch()
        return gitPull(branch_name)

    elif operation == "branch":
        return getBranch()


    else:
        return f"Unsupported Git operation: {operation}"