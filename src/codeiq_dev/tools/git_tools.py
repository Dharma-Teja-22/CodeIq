import subprocess

def gitAdd(file_name: str):
    '''Add files to the Git repository'''
    result = subprocess.run(["git", "add", file_name], capture_output=True, text=True)
    if result.returncode == 0:
        return f"Added {file_name} to the Git repository"
    else:
        return f"Failed to add {file_name} to the Git repository"

def gitCommit(message: str):
    '''Commit files to the Git repository'''
    result = subprocess.run(["git", "commit", "-m", message], capture_output=True, text=True)
    if result.returncode == 0:
        return f"Committed files to the Git repository with message: {message}"
    else:
        return f"Failed to commit files to the Git repository"

# def gitPush(branch_name: str):
#     '''Push to a branch'''
#     result = subprocess.run(["git", "push", "origin", branch_name], capture_output=True, text=True)
#     if result.returncode == 0:
#         return f"Pushed to branch: {branch_name}"
#     else:
#         return f"Failed to push to branch"

# def gitPull(branch_name: str):
#     '''Pull from a branch'''
#     result = subprocess.run(["git", "pull", "origin", branch_name], capture_output=True, text=True)
#     if result.returncode == 0:
#         return f"Pulled from branch: {branch_name}"
#     else:
#         return f"Failed to pull from branch"

def getBranch():
    '''Get Current Branch Name'''
    result = subprocess.run(["git", "branch", "--show-current"], capture_output=True, text=True)
    if result.returncode == 0:
        return result.stdout.strip()
    else:
        return f"Failed to get branch name"