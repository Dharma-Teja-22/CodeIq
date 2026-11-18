from codeiq_dev.tools.miscellaneous_tools import executeTool
from codeiq_dev.tools.file_tools import fileOperation
from codeiq_dev.tools.git_tools import gitOperation
from codeiq_dev.tools.web_search_tool import DDGSearch, read_url
from codeiq_dev.core.skills import skill_manager

from typing import Dict, Any, List, Optional

def run_skill(skill_identifier: str) -> str:
    """
    Locates, loads, and executes the specified skill by name or path within the sandbox environment,
    saving the resulting outputs into the Skill_results directory.
    """
    try:
        results_dir = skill_manager.execute_skill(skill_identifier)
        return f"Successfully executed skill '{skill_identifier}'. Output saved to: {results_dir}"
    except Exception as e:
        return f"Error executing skill '{skill_identifier}': {str(e)}"

# Tool schemas available for LLM function calling
tool_schema: List[Dict[str, Any]] = [
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
                            "branch",
                        ],
                        "description": "The Git operation to perform.",
                    },
                    "file_name": {
                        "type": "string",
                        "description": (
                            "File or directory to stage. "
                            "Use '.' for all changes."
                        ),
                    },
                    "commit_message": {
                        "type": "string",
                        "description": "Message to use for a commit.",
                    },
                },
                "required": ["operation"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fileOperations",
            "description": (
                "Perform file operations. "
                "read_file: Read content of a file. "
                "write_file: Write or create a completely new file when explicitly requested. DO NOT use write_file to duplicate an existing file when fixing errors. "
                "replace_content: Replace an existing specific block of code in an existing file with corrected or updated code. "
                "find_file: Search for a file by name. "
                "Note: For skill-related tasks, generated files and temporary scripts must be created inside ~/.codeiq/sandbox/."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": ["read_file", "write_file", "replace_content", "find_file"],
                        "description": "The file operation to perform.",
                    },
                    "file_path": {
                        "type": "string",
                        "description": "Relative or absolute path to the file (e.g. 'src/app.py' or 'C:/Users/dlankada/.codeiq/sandbox/script.py').",
                    },
                    "content": {
                        "type": "string",
                        "description": "Content to write (for write_file).",
                    },
                    "old_code": {
                        "type": "string",
                        "description": "Exact existing code snippet to be replaced (for replace_content).",
                    },
                    "new_code": {
                        "type": "string",
                        "description": "New replacement code snippet (for replace_content).",
                    },
                },
                "required": ["operation", "file_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "executeTool",
            "description": (
                "Execute a single short-running, non-interactive terminal command. This tool is intended for operations that complete quickly and return a finite output, such as listing files, inspecting project structure, checking Git status, installing specific packages, running unit tests, checking dependency versions, or executing short scripts. For skill-related operations (such as npm install, pip install, node script execution, python script execution), pass cwd pointing to ~/.codeiq/sandbox or execute within ~/.codeiq/sandbox so the main repository is not polluted. Before execution, always present the exact generated command to the user and obtain explicit confirmation. Never execute a command without approval. Do not use this tool for continuous, background, interactive, persistent, or long-running processes."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The exact, complete terminal command that needs to be executed.",
                    },
                    "cwd": {
                        "type": "string",
                        "description": "Optional working directory in which to execute the command (e.g. 'C:/Users/dlankada/.codeiq/sandbox' for skill operations).",
                    },
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "webSearch",
            "description": "Search the web using DuckDuckGo to obtain up-to-date documentation, error fixes, articles, and answers.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query string."
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetchWebpageMarkdown",
            "description": "Fetch and extract clean markdown content and text from a specific web URL using Jina AI Reader.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The complete HTTP/HTTPS URL of the webpage to fetch."
                    }
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "executeSkill",
            "description": (
                "Execute a specialized skill loaded in the system by name or path. "
                "Use this tool whenever the user's request matches an available specialized skill (e.g., pdf, docx, pptx, xlsx, frontend-design) "
                "or when the user explicitly requests to run/apply a skill by name or path. "
                "The skill executes in the sandbox at ~/.codeiq/sandbox and all final outputs are rendered exclusively into the project's Skill_results directory."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "skill_name": {
                        "type": "string",
                        "description": "The name or path of the skill to execute (e.g., 'pdf', 'docx', 'xlsx', 'pptx', 'frontend-design', or a file/folder path).",
                    }
                },
                "required": ["skill_name"],
            },
        },
    },
]

# Tools
tools = {
    "gitOperations": gitOperation,
    "fileOperations": fileOperation,
    "executeTool": executeTool,
    "webSearch": DDGSearch,
    "fetchWebpageMarkdown": read_url,
    "executeSkill": run_skill,
}
