# ⚡ CodeIq

> **An OpenCode-like AI coding assistant that runs entirely in your terminal with a rich TUI.**
> No web frontend. No database. No cloud deployment. 100% Local-First.

```
   ______          __     ____        
  / ____/___  ____/ /__  /  _/___ _   
 / /   / __ \/ __  / _ \ / // __ `/   
/ /___/ /_/ / /_/ /  __// // /_/ /    
\____/\____/\__,_/\___/___/\__, /     
                             /_/      
Terminal AI Coding Assistant • v1.0.0
```

---

## 🌟 Key Highlights

- **🖥️ 100% Terminal-Native TUI**: Built with [Textual](https://textual.textualize.io/) and [Rich](https://rich.readthedocs.io/) featuring a modern, dark aesthetic (Catppuccin / Tokyo Night inspired), responsive split layouts, and smooth navigation.
- **📂 Automatic Directory & File Exploration**: Automatically detects the current working directory, renders a responsive workspace tree explorer, and honors `.gitignore` and `.codeiqignore`.
- **⚡ Primary Provider: Google Gemini**: Deep integration with Gemini models (`gemini-2.5-flash`, `gemini-2.5-pro`, `gemini-2.0-flash`, `gemini-1.5-pro`) using the official `google-genai` SDK with real-time token streaming and function calling.
- **🔄 Multi-Provider Extensibility**: Plug-and-play support for **OpenAI** (`gpt-4o`, `gpt-4o-mini`, `o3-mini`), **Groq** (`llama-3.3-70b`), and **Ollama** (offline local models) via configurable API keys and endpoints.
- **🛡️ Approval Before Risky Operations**: Interactive approval modal intercepting destructive commands, arbitrary shell executions, and file modifications with one-click **[Approve (Enter)]**, **[Reject (Esc)]**, and **[Always Approve (A)]**.
- **📄 Unified Colored Diff Previews**: Every file creation or surgical code replacement displays unified diff previews with green additions (`+`), red deletions (`-`), and cyan chunk headers.
- **🌱 Native Git Integration**: Real-time status indicator (`🌱 main (~2 +1)`), commit logs, workspace diffs, and staged commits directly in the TUI.
- **🧠 Context-Aware Code Assistance**: Workspace indexing with automatic `@filename` mention expansion—mentioning `@path` embeds file contents directly into the prompt.
- **📊 Real-Time Token & Cost Tracking**: Live calculation of prompt tokens, completion tokens, total tokens, and dollar cost based on model pricing tables.
- **💾 Local-First JSON Sessions**: Automatic persistence in `.codeiq/sessions/*.json`. Resume, list, fork, delete, or export conversations to Markdown at any time.

---

## 🚀 Quick Start

### 1. Installation

Install in editable mode inside your project directory:

```bash
git clone <repo-url> CodeIq
cd CodeIq
pip install -e .
```

### 2. Configure API Key

CodeIq uses **Gemini** as the primary LLM provider. Set your API key:

```bash
# In your terminal or in a .env file:
export GEMINI_API_KEY="your-gemini-api-key"

# On Windows PowerShell:
$env:GEMINI_API_KEY="your-gemini-api-key"
```

*(You can also press `Ctrl+S` anytime inside the application to enter or change API keys and switch providers).*

### 3. Launch CodeIq

Launch CodeIq directly in any project folder:

```bash
codeiq
```

Or target a specific folder or model:

```bash
codeiq --dir /path/to/project --model gemini-2.5-pro
```

---

## ⌨️ Keyboard Shortcuts

| Shortcut | Description |
| :--- | :--- |
| **`Ctrl + B`** | Toggle Project File Explorer sidebar |
| **`Ctrl + S`** | Open Settings & Multi-Provider Model Picker |
| **`Ctrl + N`** | Start a fresh Coding Session |
| **`Ctrl + O`** | Open Session History (Resume / Export / Delete) |
| **`Ctrl + L`** | Clear active Chat View (preserves session history) |
| **`Ctrl + Q`** | Exit CodeIq |
| **`Enter`** | Submit message to AI Agent |

---

## 💬 Slash Commands

Type these directly into the chat prompt:

- **`/help`** — Show complete command manual
- **`/exit`** (or **`/quit`**) — Exit and close the CodeIq TUI immediately
- **`/git`** — Display current Git branch and repository modifications
- **`/diff`** — View unified Git diff of unstaged/staged workspace changes
- **`/sessions`** (or **`/resume`**) — Open session manager dialog
- **`/model <name>`** — Switch active model on the fly (e.g. `/model gemini-2.5-pro`)
- **`/provider <name>`** — Switch provider (`gemini`, `openai`, `groq`, `ollama`)
- **`/stats`** (or **`/cost`**) — View cumulative session token usage and estimated dollar cost
- **`/autoapprove`** — Toggle auto-approval mode on or off
- **`/files`** — Toggle project file explorer sidebar
- **`/clear`** — Clear screen
- **`/export`** — Export current conversation transcript to Markdown

---

## 🛠️ Built-in AI Agent Tools

The CodeIq agent operates autonomously using a suite of local workspace tools:

1. `read_file(path, start_line, end_line)` — Reads file contents with line numbering.
2. `write_file(path, content)` — Creates or overwrites files (triggers Diff Preview & Approval).
3. `edit_file(path, old_str, new_str)` — Surgical string replacement with strict uniqueness check.
4. `list_dir(path, recursive, depth)` — Inspects folders respecting ignore patterns.
5. `search_files(pattern, path)` — Glob pattern search across directory trees.
6. `grep_search(query, path, is_regex)` — High-speed text search across codebase files.
7. `execute_command(command, timeout)` — Executes shell commands with live stdout/stderr capture.
8. `git_status()` — Inspects staged, modified, and untracked files.
9. `git_diff(file_path, staged)` — Produces unified git diffs.
10. `git_log(max_count)` — Retrieves commit history.
11. `git_commit(message)` — Stages tracked modifications and commits changes.

---

## 📁 Architecture

```
d:\Desktop\CodeIq\
│
├── codeiq/
│   ├── cli.py                    # Argument parsing, CLI flags, bootstrap
│   ├── config.py                 # Configuration manager (.env, .codeiq/config.json)
│   ├── models.py                 # Core data structures (Session, Message, ToolCall, DiffChunk)
│   │
│   ├── agent/                    # Autonomous AI Coding Agent
│   │   ├── agent.py              # Main multi-turn reasoning and tool-calling loop
│   │   ├── context.py            # Project tree scanner & @file mention resolver
│   │   └── prompts.py            # System prompts with CWD & Git context
│   │
│   ├── diff/                     # File diffing & preview utilities
│   │   └── diff_engine.py        # Unified diff generator & addition/deletion counter
│   │
│   ├── llm/                      # Multi-provider LLM abstraction
│   │   ├── base.py               # Abstract provider interface (streaming, tools)
│   │   ├── gemini.py             # Primary Google Gemini provider (google-genai SDK)
│   │   ├── openai_provider.py    # OpenAI, Groq, Ollama, OpenRouter provider
│   │   ├── factory.py            # Provider instantiator & model catalog
│   │   └── pricing.py            # Real-time token rate calculator & cost tracker
│   │
│   ├── storage/                  # Local-first persistence
│   │   └── session_store.py      # SessionManager (.codeiq/sessions/*.json)
│   │
│   ├── tools/                    # Tool registry and execution
│   │   ├── base_tools.py / bash  # Terminal shell execution with risk detection
│   │   ├── file_tools.py         # File exploration, reading, and editing
│   │   ├── git_tools.py          # Native Git integration
│   │   └── registry.py           # Central registry & schema generator
│   │
│   └── tui/                      # Textual User Interface
│       ├── app.py                # Main CodeIqApp Textual application
│       ├── styles.tcss           # Sleek Catppuccin / Tokyo Night terminal styling
│       ├── widgets/              # MessageBubble, ToolBubble, DiffViewer, FileTree, StatusBar
│       └── modals/               # ApprovalModal, SettingsModal, SessionManagerModal
│
├── tests/                        # Comprehensive test suite (pytest & async TUI tests)
├── pyproject.toml
├── setup.py
└── README.md
```

---

## 🧪 Testing

CodeIq includes a 100% passing test suite covering unit tests, integration tests, and asynchronous TUI pilot testing:

```bash
pytest tests/
```

Output:
```
tests/test_agent_flow.py ...                                             [ 23%]
tests/test_codeiq.py ........                                            [ 84%]
tests/test_tui.py ..                                                     [100%]
============================= 13 passed in 10.31s =============================
```

---

## 📄 License

MIT License. Designed and crafted for terminal power users.
