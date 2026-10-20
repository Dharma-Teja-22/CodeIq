"""Central tool registry, schema generator, and execution dispatcher."""

from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..diff.diff_engine import DiffEngine
from .file_tools import edit_file, grep_search, list_dir, read_file, search_files, write_file
from .bash_tools import execute_command_sync, is_risky_command
from .git_tools import git_commit, git_diff, git_log, git_status


@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: Dict[str, Any]
    handler: Callable[..., Any]
    requires_approval: bool = False
    is_risky_check: Optional[Callable[[Dict[str, Any]], bool]] = None


class ToolRegistry:
    """Manages all available tools and their schemas."""

    def __init__(self, cwd: Optional[Path] = None):
        self.cwd = (cwd or Path.cwd()).resolve()
        self.tools: Dict[str, ToolDefinition] = {}
        self._register_default_tools()

    def register(self, tool: ToolDefinition) -> None:
        self.tools[tool.name] = tool

    def get_tool(self, name: str) -> Optional[ToolDefinition]:
        return self.tools.get(name)

    def _register_default_tools(self) -> None:
        # 1. read_file
        self.register(
            ToolDefinition(
                name="read_file",
                description="Reads the contents of a file with line numbers. You can specify a line range.",
                parameters={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "The file path relative to workspace or absolute."},
                        "start_line": {"type": "integer", "description": "Optional start line number (1-based)."},
                        "end_line": {"type": "integer", "description": "Optional end line number (1-based, inclusive)."},
                    },
                    "required": ["path"],
                },
                handler=lambda path, start_line=None, end_line=None: read_file(path, start_line, end_line, self.cwd),
                requires_approval=False,
            )
        )

        # 2. write_file
        self.register(
            ToolDefinition(
                name="write_file",
                description="Creates a new file or completely replaces the content of an existing file.",
                parameters={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "The relative or absolute file path to write."},
                        "content": {"type": "string", "description": "The full text content to write to the file."},
                    },
                    "required": ["path", "content"],
                },
                handler=lambda path, content: write_file(path, content, self.cwd),
                requires_approval=True,
            )
        )

        # 3. edit_file
        self.register(
            ToolDefinition(
                name="edit_file",
                description="Replaces a unique target code snippet (old_str) with new code (new_str) in an existing file.",
                parameters={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "The file path to edit."},
                        "old_str": {"type": "string", "description": "The exact existing text block to be replaced."},
                        "new_str": {"type": "string", "description": "The replacement text block."},
                    },
                    "required": ["path", "old_str", "new_str"],
                },
                handler=lambda path, old_str, new_str: edit_file(path, old_str, new_str, self.cwd),
                requires_approval=True,
            )
        )

        # 4. list_dir
        self.register(
            ToolDefinition(
                name="list_dir",
                description="Lists files and subdirectories in a folder, respecting ignore files.",
                parameters={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "The directory path (default: current directory '.')."},
                        "recursive": {"type": "boolean", "description": "Whether to list subdirectories recursively."},
                        "depth": {"type": "integer", "description": "Max recursion depth (default: 2)."},
                    },
                },
                handler=lambda path=".", recursive=False, depth=2: list_dir(path, recursive, depth, self.cwd),
                requires_approval=False,
            )
        )

        # 5. search_files
        self.register(
            ToolDefinition(
                name="search_files",
                description="Searches for files matching a glob pattern (e.g. '*.py' or 'test_*.ts').",
                parameters={
                    "type": "object",
                    "properties": {
                        "pattern": {"type": "string", "description": "Glob pattern to match file names."},
                        "path": {"type": "string", "description": "Directory to search in (default: '.')."},
                    },
                    "required": ["pattern"],
                },
                handler=lambda pattern, path=".": search_files(pattern, path, self.cwd),
                requires_approval=False,
            )
        )

        # 6. grep_search
        self.register(
            ToolDefinition(
                name="grep_search",
                description="Searches for a text pattern inside project files, returning line numbers and snippets.",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "The text pattern to find."},
                        "path": {"type": "string", "description": "Directory or file to search in (default: '.')."},
                        "is_regex": {"type": "boolean", "description": "Whether query is a regular expression."},
                    },
                    "required": ["query"],
                },
                handler=lambda query, path=".", is_regex=False: grep_search(query, path, is_regex, self.cwd),
                requires_approval=False,
            )
        )

        # 7. execute_command
        self.register(
            ToolDefinition(
                name="execute_command",
                description="Executes a shell command in the workspace terminal and returns stdout/stderr.",
                parameters={
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "The command line string to run."},
                        "timeout": {"type": "integer", "description": "Timeout in seconds (default: 60)."},
                    },
                    "required": ["command"],
                },
                handler=lambda command, timeout=60: execute_command_sync(command, self.cwd, timeout)[1],
                requires_approval=True,
                is_risky_check=lambda args: is_risky_command(args.get("command", "")),
            )
        )

        # 8. git_status
        self.register(
            ToolDefinition(
                name="git_status",
                description="Shows current Git branch, modified files, staged files, and untracked files.",
                parameters={"type": "object", "properties": {}},
                handler=lambda: git_status(self.cwd),
                requires_approval=False,
            )
        )

        # 9. git_diff
        self.register(
            ToolDefinition(
                name="git_diff",
                description="Shows unified diff of uncommitted changes in the Git repository.",
                parameters={
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "Optional specific file to diff."},
                        "staged": {"type": "boolean", "description": "Whether to view staged changes."},
                    },
                },
                handler=lambda file_path=None, staged=False: git_diff(file_path, staged, self.cwd),
                requires_approval=False,
            )
        )

        # 10. git_log
        self.register(
            ToolDefinition(
                name="git_log",
                description="Shows recent Git commit log entries.",
                parameters={
                    "type": "object",
                    "properties": {
                        "max_count": {"type": "integer", "description": "Number of commits to show (default: 5)."},
                    },
                },
                handler=lambda max_count=5: git_log(max_count, self.cwd),
                requires_approval=False,
            )
        )

        # 11. git_commit
        self.register(
            ToolDefinition(
                name="git_commit",
                description="Stages tracked modified files and commits them with the given message.",
                parameters={
                    "type": "object",
                    "properties": {
                        "message": {"type": "string", "description": "The git commit message."},
                    },
                    "required": ["message"],
                },
                handler=lambda message: git_commit(message, self.cwd),
                requires_approval=True,
            )
        )

    def is_approval_needed(self, name: str, args: Dict[str, Any], auto_approve: bool = False) -> bool:
        if auto_approve:
            # Even in auto-approve mode, verify high-risk destructive shell commands
            tool = self.tools.get(name)
            if tool and tool.is_risky_check and tool.is_risky_check(args):
                return True
            return False

        tool = self.tools.get(name)
        if not tool:
            return False
        return tool.requires_approval

    def generate_diff_preview(self, name: str, args: Dict[str, Any]) -> Optional[str]:
        """Generates unified diff preview for write_file and edit_file."""
        if name == "write_file":
            path_str = args.get("path", "")
            content = args.get("content", "")
            target = (self.cwd / path_str).resolve() if not Path(path_str).is_absolute() else Path(path_str)
            res = DiffEngine.preview_write(target, content)
            return res.diff_text

        elif name == "edit_file":
            path_str = args.get("path", "")
            old_str = args.get("old_str", "")
            new_str = args.get("new_str", "")
            target = (self.cwd / path_str).resolve() if not Path(path_str).is_absolute() else Path(path_str)
            res = DiffEngine.preview_edit(target, old_str, new_str)
            return res.diff_text if res else None

        elif name == "execute_command":
            cmd = args.get("command", "")
            return f"$ {cmd}\n(Directory: {self.cwd})"

        return None

    def execute(self, name: str, args: Dict[str, Any]) -> str:
        tool = self.tools.get(name)
        if not tool:
            return f"Error: Tool '{name}' not found in registry."
        try:
            return str(tool.handler(**args))
        except TypeError as e:
            return f"Error executing tool '{name}' with args {args}: {e}"
        except Exception as e:
            return f"Exception in tool '{name}': {e}"

    def to_gemini_tools(self) -> List[Dict[str, Any]]:
        """Converts tools into Gemini function declarations format."""
        declarations = []
        for tool in self.tools.values():
            declarations.append({
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            })
        return [{"function_declarations": declarations}]

    def to_openai_tools(self) -> List[Dict[str, Any]]:
        """Converts tools into OpenAI function calling format."""
        tools = []
        for tool in self.tools.values():
            tools.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            })
        return tools
