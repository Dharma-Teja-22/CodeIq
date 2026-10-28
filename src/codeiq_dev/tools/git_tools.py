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