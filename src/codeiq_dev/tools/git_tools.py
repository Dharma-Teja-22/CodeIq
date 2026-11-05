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
    """
    Stage new, modified, and deleted files in the Git repository.

    Args:
        file_name (str): File or directory path to stage. Defaults to "." for all changes.

    Returns:
        str: Status message indicating whether changes were staged successfully or failed.
    """
    try:
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
    except Exception as e:
        return f"Error executing git add: {str(e)}"

def gitDiff() -> str:
    """
    Get the diff of currently staged changes.

    Args:
        None

    Returns:
        str: Git diff output of cached changes or an error message if it fails.
    """
    try:
        result = subprocess.run(["git", "diff", "--cached"], capture_output=True, text=True)
        if result.returncode == 0:
            return result.stdout.strip()
        else:
            err = result.stderr.strip()
            return f"Failed to get the diff: {err}" if err else "Failed to get the diff"
    except Exception as e:
        return f"Error executing git diff: {str(e)}"

def gitCommit(message: str) -> str:
    """
    Commit staged changes using the provided message.

    Args:
        message (str): Commit message describing the changes.

    Returns:
        str: Confirmation message with commit status or error details.
    """
    try:
        result = subprocess.run(
            ["git", "commit", "-m", message],
            capture_output=True,
            text=True,
        )

        if result.returncode == 0:
            return f"Commit successful: {message}"

        return f"Commit failed: {result.stderr.strip()}"
    except Exception as e:
        return f"Error executing git commit: {str(e)}"

def gitPush(branch_name: str) -> str:
    """
    Push committed changes to the specified remote branch.

    Args:
        branch_name (str): The name of the remote branch to push to.

    Returns:
        str: Confirmation message on success or failure notice.
    """
    try:
        result = subprocess.run(["git", "push", "origin", branch_name], capture_output=True, text=True)
        if result.returncode == 0:
            return f"Pushed to branch: {branch_name}"
        else:
            err = result.stderr.strip()
            return f"Failed to push to branch: {err}" if err else "Failed to push to branch"
    except Exception as e:
        return f"Error executing git push: {str(e)}"

def gitPull(branch_name: str) -> str:
    """
    Pull latest changes from the specified remote branch.

    Args:
        branch_name (str): The name of the remote branch to pull from.

    Returns:
        str: Confirmation message on success or failure notice.
    """
    try:
        result = subprocess.run(["git", "pull", "origin", branch_name], capture_output=True, text=True)
        if result.returncode == 0:
            return f"Pulled from branch: {branch_name}"
        else:
            err = result.stderr.strip()
            return f"Failed to pull from branch: {err}" if err else "Failed to pull from branch"
    except Exception as e:
        return f"Error executing git pull: {str(e)}"

def getBranch() -> str:
    """
    Get the current active Git branch name.

    Args:
        None

    Returns:
        str: Name of the current Git branch or failure notice.
    """
    try:
        result = subprocess.run(["git", "branch", "--show-current"], capture_output=True, text=True)
        if result.returncode == 0:
            return result.stdout.strip()
        else:
            err = result.stderr.strip()
            return f"Failed to get branch name: {err}" if err else "Failed to get branch name"
    except Exception as e:
        return f"Error retrieving git branch: {str(e)}"

def gitOperation(operation: str, file_name: str = ".", commit_message: str = "") -> str:
    """
    Dispatch and execute a requested Git operation.

    Args:
        operation (str): Name of the Git operation ('add', 'commit', 'push', 'pull', 'branch').
        file_name (str): File or directory path to stage for 'add'. Defaults to ".".
        commit_message (str): Commit message to use for 'commit'. Defaults to "".

    Returns:
        str: Result or status message from the executed Git operation.
    """
    try:
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
    except Exception as e:
        return f"Error performing Git operation '{operation}': {str(e)}"