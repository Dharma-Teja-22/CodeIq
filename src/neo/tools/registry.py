from neo.tools.miscellaneous_tools import executeTool
from neo.tools.file_tools import fileOperation
from neo.tools.git_tools import gitOperation
from neo.tools.web_search_tool import DDGSearch, read_url
from neo.core.skills import skill_manager
from neo.tools.memory_tools import (
    updateProjectMemory,
    saveToGlobalMemory,
    recallEpisodicMemory,
    logSuccessfulDebug,
    saveConcept,
)

from typing import Dict, Any, List, Optional

def run_skill(skill_identifier: str) -> str:
    """
    Locates, loads, and executes the specified skill by name or path within the sandbox environment,
    saving the resulting outputs into the sandbox Skill_result directory (~/.neo/sandbox/Skill_result).
    """
    try:
        results_dir, message = skill_manager.execute_skill(skill_identifier)
        return message
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
                            "Use '.' for all changes, or specify individual file names."
                        ),
                    },
                    "exclude": {
                        "type": "string",
                        "description": (
                            "File, files (comma or space separated), or pattern to exclude from staging or committing. "
                            "Use this whenever the user asks to commit or stage changes while excluding specific files (e.g. 'exclude file.py', 'except test.txt')."
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
                "Note: For skill-related tasks, all generated files, outputs, and temporary scripts must be stored exclusively inside ~/.neo/sandbox/ or ~/.neo/sandbox/Skill_result/ and NEVER in the project repository."
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
                        "description": "Relative or absolute path to the file (e.g. 'src/app.py' or 'C:/Users/dlankada/.neo/sandbox/script.py').",
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
                "Execute a single short-running, non-interactive terminal command. This tool is intended for operations that complete quickly and return a finite output, such as listing files, inspecting project structure, checking Git status, installing specific packages, running unit tests, checking dependency versions, or executing short scripts. For skill-related operations (such as npm install, pip install, node script execution, python script execution), pass cwd pointing to ~/.neo/sandbox so all installs and operations happen inside the sandbox only and never in the repo. Before execution, always present the exact generated command to the user and obtain explicit confirmation. Never execute a command without approval. Do not use this tool for continuous, background, interactive, persistent, or long-running processes."
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
                        "description": "Optional working directory in which to execute the command (e.g. 'C:/Users/dlankada/.neo/sandbox' for skill operations).",
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
                "The skill executes strictly in the sandbox at ~/.neo/sandbox and all final outputs are rendered exclusively into ~/.neo/sandbox/Skill_result. "
                "Never write or output generated skill files to the main repository. "
                "IMPORTANT: Invoke this tool only ONCE per user request. Once executed and returned, do NOT call executeSkill again; formulate and present the final answer directly to the user."
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
    {
        "type": "function",
        "function": {
            "name": "updateProjectMemory",
            "description": (
                "Atomically update a section in the active project's working memory (~/.neo/memory/projects/{project}.md). "
                "Canonical sections: 'Tech Stack & Runtime', 'Active Architecture & Key Modules', 'Critical Constraints, Preferences', 'Current/Ongoing Tasks'. "
                "Mode can be 'replace' (recommended for Current/Ongoing Tasks) or 'append' (to add bullet items)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "section": {
                        "type": "string",
                        "description": "The target section name (e.g. 'Tech Stack & Runtime', 'Active Architecture & Key Modules', 'Critical Constraints, Preferences', 'Current/Ongoing Tasks').",
                    },
                    "content": {
                        "type": "string",
                        "description": "Markdown content/bullets to update into the section.",
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["replace", "append"],
                        "description": "Update mode: 'replace' to overwrite section body, or 'append' to add lines.",
                    },
                },
                "required": ["section", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "saveToGlobalMemory",
            "description": (
                "Save cross-project user facts, environment info, or persistent preferences to ~/.neo/memory/global_memory.md. "
                "Automatically handles deduplication and overwrites/supersedes conflicting preferences (e.g. updating formatting rules)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "information": {
                        "type": "string",
                        "description": "The preference, rule, constraint, or fact to store.",
                    },
                    "category": {
                        "type": "string",
                        "description": "Category label (e.g. 'Preference', 'Environment', 'Constraint'). Defaults to 'Preference'.",
                    },
                },
                "required": ["information"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recallEpisodicMemory",
            "description": (
                "Search past bug solutions, verified fixes, and codebase architectural concepts using pure-Python Okapi BM25 ranking engine (< 2ms). "
                "Call this whenever answering questions about previously resolved errors, concepts, or past debugging history."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Keywords or natural language search query for the issue or concept to retrieve.",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "logSuccessfulDebug",
            "description": "Log a verified bug fix and solution into episodic debug history (~/.neo/memory/debug_history.md).",
            "parameters": {
                "type": "object",
                "properties": {
                    "error_description": {
                        "type": "string",
                        "description": "Clear description of the error or failure encountered.",
                    },
                    "solution": {
                        "type": "string",
                        "description": "The exact solution, steps, or code adjustments that successfully resolved the issue.",
                    },
                },
                "required": ["error_description", "solution"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "saveConcept",
            "description": "Save an architectural pattern or deep conceptual doc into episodic concepts (~/.neo/memory/concepts/{concept_name}.md).",
            "parameters": {
                "type": "object",
                "properties": {
                    "concept_name": {
                        "type": "string",
                        "description": "Short identifier/name of the concept (e.g. 'caching_strategy', 'auth_pipeline').",
                    },
                    "explanation": {
                        "type": "string",
                        "description": "Detailed architectural explanation and design notes.",
                    },
                },
                "required": ["concept_name", "explanation"],
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
    "updateProjectMemory": updateProjectMemory,
    "saveToGlobalMemory": saveToGlobalMemory,
    "recallEpisodicMemory": recallEpisodicMemory,
    "logSuccessfulDebug": logSuccessfulDebug,
    "saveConcept": saveConcept,
}
