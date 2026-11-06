from codeiq_dev.tools.miscellaneous_tools import executeTool
from codeiq_dev.tools.file_tools import fileOperation
from codeiq_dev.tools.git_tools import gitOperation
from codeiq_dev.tools.web_search_tool import DDGSearch, read_url

from typing import Dict, Any, List

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
                "Perform file operations in the project. "
                "read_file: Read content of a file. "
                "write_file: Write or create a completely new file when explicitly requested. DO NOT use write_file to duplicate an existing file when fixing errors. "
                "replace_content: Replace an existing specific block of code in an existing file with corrected or updated code. "
                "find_file: Search for a file by name."
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
                        "description": "Relative or absolute path to the file (e.g. 'src/app.py' or 'app.py').",
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
                "Execute a single short-running, non-interactive terminal command in the user's project environment. This tool is intended for operations that complete quickly and return a finite output, such as listing files, inspecting project structure, checking Git status, installing specific packages, running unit tests, checking dependency versions, or executing short scripts. Before execution, always present the exact generated command to the user and obtain explicit confirmation. Never execute a command without approval. Do not use this tool for continuous, background, interactive, persistent, or long-running processes, including development servers, production servers, file watchers, monitoring utilities, interactive shells, REPL sessions, or commands that wait indefinitely for input. Examples of prohibited commands include npm start, npm run dev, yarn dev, pnpm dev, vite, nodemon, next dev, uvicorn, gunicorn, flask run, streamlit run, watch, top, htop, and tail -f. Never bypass these restrictions through command chaining, shell wrappers, or background execution. If the requested operation requires a continuous or long-running process, inform the user that it is not supported instead of invoking this tool. Execute only commands directly related to the user's request, enforce the configured execution timeout, and report the execution result clearly. If execution fails or times out, communicate the error without automatically retrying. Keep the returned output concise and limit it to approximately 350 characters, clearly indicating when the output has been truncated."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The exact, complete terminal command that needs to be executed. Provide only one short-running, non-interactive command that is directly relevant to the user's request and is expected to complete within the configured timeout. Do not include explanations, Markdown formatting, or additional instructions. Avoid destructive or irreversible operations unless explicitly authorized. Do not provide commands that start servers, background processes, watchers, monitoring utilities, interactive shells, REPL sessions, infinite loops, or processes that require continuous execution. Do not chain multiple commands using &&, ||, ;, pipes, or shell wrappers to bypass execution restrictions. The command must be suitable for execution in the user's project environment and must be presented to the user for explicit approval before execution.",
                    }
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

]

# Tools
tools = {
    "gitOperations": gitOperation,
    "fileOperations": fileOperation,
    "executeTool": executeTool,
    "webSearch": DDGSearch,
    "fetchWebpageMarkdown": read_url
}