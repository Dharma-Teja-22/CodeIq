from dotenv import load_dotenv
from openai import OpenAI
import subprocess
from neo.core.settings import settings

load_dotenv()

client = OpenAI(
    api_key=settings.GEMINI_API_KEY,
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
)

def gitAdd(file_name: str = ".", exclude: str = "") -> str:
    """
    Stage new, modified, and deleted files in the Git repository,
    optionally excluding specific file paths or patterns.

    Args:
        file_name (str): File, files, or directory path to stage. Defaults to "." for all changes.
                         Multiple files can be comma- or space-separated.
        exclude (str): File, files, or pattern to exclude from staging.
                       If specified, the excluded paths will never be staged.

    Returns:
        str: Status message indicating whether changes were staged successfully or failed.
    """
    try:
        # Parse excluded file paths if provided
        excluded_files = []
        if exclude and exclude.strip():
            # Support comma, semicolon, or whitespace separation
            raw_excludes = [x.strip() for x in exclude.replace(",", " ").replace(";", " ").split()]
            excluded_files = [x for x in raw_excludes if x]

        # Case 1: Staging everything ("." or empty) with exclusions
        if file_name in [".", "", None] and excluded_files:
            # 1. Stage all files first
            res_add = subprocess.run(["git", "add", "-A"], capture_output=True, text=True)
            if res_add.returncode != 0:
                return f"Failed to stage changes: {res_add.stderr.strip()}"
            
            # 2. Unstage all excluded files
            unstage_errors = []
            for exc in excluded_files:
                res_reset = subprocess.run(["git", "reset", "HEAD", "--", exc], capture_output=True, text=True)
                if res_reset.returncode != 0:
                    unstage_errors.append(res_reset.stderr.strip())
            
            if unstage_errors:
                return f"Staged changes except {', '.join(excluded_files)}, but encountered issues unstaging: {'; '.join(unstage_errors)}"
            return f"Successfully staged changes excluding: {', '.join(excluded_files)}"

        # Case 2: Staging specific files (or comma/space separated list of files)
        if file_name and file_name != ".":
            # Check if multiple targets were passed
            raw_targets = [x.strip() for x in file_name.replace(",", " ").replace(";", " ").split()]
            targets = [x for x in raw_targets if x and x not in excluded_files]
            
            if not targets:
                return f"No files staged. All specified targets were excluded: {', '.join(excluded_files)}"

            cmd = ["git", "add", "--"] + targets
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                return f"Successfully staged changes: {', '.join(targets)}"
            return f"Failed to stage changes: {result.stderr.strip()}"

        # Case 3: Default add all without exclusion
        result = subprocess.run(
            ["git", "add", "-A"],
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

def gitCommit(message: str, exclude: str = "") -> str:
    """
    Commit staged changes using the provided message, ensuring any excluded files
    are un-staged before the commit occurs.

    Args:
        message (str): Commit message describing the changes.
        exclude (str): File, files, or pattern to exclude from the commit.

    Returns:
        str: Confirmation message with commit status or error details.
    """
    try:
        # If files were excluded, ensure they are un-staged before committing
        if exclude and exclude.strip():
            raw_excludes = [x.strip() for x in exclude.replace(",", " ").replace(";", " ").split()]
            for exc in raw_excludes:
                if exc:
                    subprocess.run(["git", "reset", "HEAD", "--", exc], capture_output=True, text=True)

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

def gitOperation(operation: str, file_name: str = ".", commit_message: str = "", exclude: str = "") -> str:
    """
    Dispatch and execute a requested Git operation.

    Args:
        operation (str): Name of the Git operation ('add', 'commit', 'push', 'pull', 'branch').
        file_name (str): File or directory path to stage for 'add'. Defaults to ".".
        commit_message (str): Commit message to use for 'commit'. Defaults to "".
        exclude (str): File or pattern to exclude from staging or committing. Defaults to "".

    Returns:
        str: Result or status message from the executed Git operation.
    """
    try:
        if operation == "add":
            return gitAdd(file_name, exclude=exclude)
        
        if operation == "commit":
            return gitCommit(commit_message, exclude=exclude)

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