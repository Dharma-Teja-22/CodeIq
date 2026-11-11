from openai import AsyncOpenAI
from typing import Dict, Any, List, Optional
import logging
# Tenacity : Exponential Backoff with built in Jitter 
from tenacity import (
    retry,
    stop_after_attempt,
    wait_random_exponential,
    retry_if_exception,
    before_log,
    after_log
)
from codeiq_dev.core.settings import settings
from codeiq_dev.tools.registry import tool_schema as tools

logger = logging.getLogger(__name__)
#-----------------------------------------------------------------------------------------------------------
from codeiq_dev.core.opik_tracker import init_opik, get_opik_client

# Initialize Opik if configured
init_opik()
#-----------------------------------------------------------------------------------------------------------
_client: Optional[AsyncOpenAI] = None

def get_client() -> AsyncOpenAI:
    global _client
    if _client is None or getattr(_client, "_is_closed", False):
        _client = AsyncOpenAI(
            api_key=settings.GEMINI_API_KEY,
            base_url=settings.GEMINI_BASE_URL,
        )
    return _client

_ALLOWED_MESSAGE_KEYS = frozenset({"role", "content", "name", "tool_call_id", "tool_calls"})


def to_llm_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Sanitize messages for the LLM API by stripping internal metadata.

    Args:
        messages (List[Dict[str, Any]]): Raw session messages.

    Returns:
        List[Dict[str, Any]]: Messages containing only keys accepted by OpenAI chat APIs.
    """
    return [
        {k: v for k, v in message.items() if k in _ALLOWED_MESSAGE_KEYS}
        for message in messages
    ]

class _ClientProxy:
    def __getattr__(self, name: str):
        return getattr(get_client(), name)

client = _ClientProxy()

async def close_client() -> None:
    """Close the AsyncOpenAI client session gracefully."""
    await client.close()

# Tool schemas available for LLM function calling
tools: List[Dict[str, Any]] = [
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
]


class AssistantMessage:
    """Helper representing an assistant turn output."""
    def __init__(self, content: str, tool_calls: list):
        self.content = content
        self.tool_calls = tool_calls

    def model_dump(self, exclude_none: bool = False) -> Dict[str, Any]:
        """
        Serialize the message into OpenAI-compatible role dictionary.

        Args:
            exclude_none (bool): Whether to omit None values. Defaults to False.

        Returns:
            Dict[str, Any]: Formatted role dictionary.
        """
        d: Dict[str, Any] = {"role": "assistant", "content": self.content}
        if self.tool_calls:
            d["tool_calls"] = [
                tc.model_dump() if hasattr(tc, "model_dump") else tc
                for tc in self.tool_calls
            ]
        return d


def _is_rate_limit_or_resource_exhausted(exception: Exception) -> bool:
    """
    Custom retry predicate for tenacity.
    Returns True if the exception indicates rate limiting (429), resource exhaustion, or quota issues.
    Explicitly ignores 401 (Unauthorized), 404 (Not Found),..etc.
    """
    error_str = str(exception).lower()
    
    # Do not retry on 401 or 404 errors
    if "401" in error_str or "unauthorized" in error_str or "404" in error_str or "not found" in error_str:
        return False
        
    # Retry on 429, resource exhaustion, or quota errors
    if "429" in error_str or "exhausted" in error_str or "quota" in error_str:
        return True
        
    return False


@retry(
    stop=stop_after_attempt(2), # Stop retrying after 5 failed attempts
    # Exponential backoff with random jitter to prevent sync spikes / thundering herd
    wait=wait_random_exponential(multiplier=1, max=16),
    retry=retry_if_exception(_is_rate_limit_or_resource_exhausted),
    before=before_log(logger, logging.INFO),
    after = after_log(logger, logging.WARNING),
    # Hook invoked right before sleeping between retries
    # before_sleep=_before_sleep_log,
    reraise=True # reraise=True ensures that if all attempts fail, the final exception is raised to the caller
)
async def _create_chat_completion_with_retry(kwargs: Dict[str, Any]):
    """
    Helper wrapper around client.chat.completions.create protected by tenacity 
    jittered exponential backoff for 429 / resource exhausted / quota errors.
    """
    return await client.chat.completions.create(**kwargs)


async def create_chat_stream(
    messages: List[Dict[str, Any]],
    model: Optional[str] = None,
    with_tools: bool = True,
):
    """
    Initiate an async streaming chat completion via the OpenAI client with exponential backoff and jitter.

    Args:
        messages (List[Dict[str, Any]]): Conversation history messages.
        model (Optional[str]): Model name or override identifier. Defaults to None.
        with_tools (bool): Whether to provide registered tool schemas. Defaults to True.

    Returns:
        AsyncStream: Asynchronous iterator of chat completion chunks.
    """
    model_name = settings.MODEL
    kwargs: Dict[str, Any] = {
        "model": model_name,
        "messages": to_llm_messages(messages),
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    if with_tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

    return await _create_chat_completion_with_retry(kwargs)


async def stream_chat_turn(
    messages: List[Dict[str, Any]],
    model: Optional[str] = None,
    with_tools: bool = True,
    on_token = None,
    on_tool_call = None,
    parent_span = None,
) -> tuple[AssistantMessage, dict]:
    """
    Handles streaming a single chat completion turn and accumulates usage metrics.

    Args:
        messages (List[Dict[str, Any]]): Message history passed to the LLM.
        model (Optional[str]): The model identifier to use. Defaults to configured model.
        with_tools (bool): Flag indicating if tool calling is enabled. Defaults to True.
        on_token (Optional[Callable]): Callback invoked on receipt of each text chunk. Defaults to None.
        on_tool_call (Optional[Callable]): Callback invoked when tool calls arrive. Defaults to None.

    Returns:
        tuple[AssistantMessage, dict]: Assistant message instance and token usage summary dictionary.
    """
    try:
        stream = await create_chat_stream(messages=messages, model=model, with_tools=with_tools)
        full_content = ""
        requested_tool_calls = []
        usage_info = {"query_tokens": 0, "completion_tokens": 0, "session_tokens": 0}

        async for chunk in stream:
            if getattr(chunk, "usage", None) and chunk.usage:
                q = chunk.usage.prompt_tokens or usage_info["query_tokens"]
                c = chunk.usage.completion_tokens or usage_info["completion_tokens"]
                usage_info["query_tokens"] = q
                usage_info["completion_tokens"] = c
                usage_info["session_tokens"] = q + c

            if getattr(chunk, "choices", None):
                for choice in chunk.choices:
                    delta = getattr(choice, "delta", None)
                    if delta:
                        if getattr(delta, "content", None):
                            content_chunk = delta.content
                            if on_token:
                                on_token(content_chunk)
                            full_content += content_chunk
                        if getattr(delta, "tool_calls", None):
                            requested_tool_calls.extend(delta.tool_calls)
                            if on_tool_call:
                                for tc in delta.tool_calls:
                                    on_tool_call(tc)

        return AssistantMessage(full_content, requested_tool_calls), usage_info

    except Exception as e:
        # Capture the exact underlying exception message (e.g. 429 Rate Limit, Quota Exceeded, etc.)
        # and return it as the assistant message so it renders directly in the UI.
        error_msg = f"Error communicating with AI service: {str(e)}"
        raise Exception(error_msg)
        # return AssistantMessage(error_msg, []), {"query_tokens": 0, "completion_tokens": 0, "session_tokens": 0}


async def generate_commit_message(diff: str, model: Optional[str] = None) -> str:
    """
    Generate a conventional Git commit message from a git diff.
    Protected by tenacity exponential backoff with jitter for 429 / resource exhaustion.

    Args:
        diff (str): The staged changes diff text.
        model (Optional[str]): Model name identifier. Defaults to None.

    Returns:
        str: Concise Conventional Commit message string.
    """
    try:
        model_name = settings.MODEL
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
        # Use our retry-wrapped helper to protect against rate limits and resource exhaustion
        response = await _create_chat_completion_with_retry({
            "model": model_name,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You generate a concise Git commit messages with the Conventional Commits format. Return only the commit message text."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
        })
        return (response.choices[0].message.content or "").strip().strip('"').strip("'")
    except Exception as e:
        return f"Error generating commit message: {str(e)}"


async def generate_session_title(user_prompt: str, model: Optional[str] = None) -> str:
    """
    Generate a concise 2-5 word title for a chat session based on the first user query.
    Protected by tenacity exponential backoff with jitter for 429 / resource exhaustion.

    Args:
        user_prompt (str): The initial prompt submitted by the user.
        model (Optional[str]): AI model identifier to use. Defaults to selected model.

    Returns:
        str: Concise title string without quotes or punctuation.
    """
    try:
        model_name = settings.SMALL_MODEL
        cleaned_prompt = user_prompt.strip()[:300]
        
        # Use our retry-wrapped helper to protect against rate limits and resource exhaustion
        response = await _create_chat_completion_with_retry({
            "model": model_name,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Generate a concise 2 to 5 word title summarizing the user's intent or topic. "
                        "Return ONLY the plain title text in title case. Do not wrap in quotes or add markdown or trailing punctuation."
                        "NOTE: ensure never provide spacing between the words(Filename must don't have speacing instead you can replace them using '_' or '-')"
                    ),
                },
                {"role": "user", "content": cleaned_prompt},
            ],
        })
        title = (response.choices[0].message.content or "").strip().strip('"').strip("'").strip("`")
        # Sanitize for safe filenames (remove illegal characters: \ / : * ? " < > |)
        sanitized = "".join(c for c in title if c.isalnum() or c in (" ", "-", "_")).strip()
        return sanitized or "New Session"
    except Exception:
        # Fallback to truncated first words if AI call fails
        words = user_prompt.strip().split()
        return " ".join(words[:4]).title() or "New Session"
