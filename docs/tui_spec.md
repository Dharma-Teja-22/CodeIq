# Neo TUI Technical Specification

## 1. Overview
This specification defines the architecture, UI/UX behavior, event contracts, and testing strategy for adding an interactive **Terminal User Interface (TUI)** to **Neo** using **Textual** (built on `rich`).

The TUI will be launched via `neo tui` while preserving all existing CLI commands and behavior in `src/neo/cli.py`.

---

## 2. Goals & Non-Goals
### Goals
- Provide a responsive, non-blocking terminal UI with split-pane layout (session sidebar + main chat area + input bar).
- Stream assistant responses as live-rendered Markdown with collapsible tool-call blocks.
- Replace blocking terminal prompts (`typer.confirm`) with an interactive TUI confirmation modal for `executeTool` and other guarded actions.
- Display live token usage and active model metadata (`Query | Completion | Session Total | Model Name`).
- Support keyboard-first navigation (`Ctrl+B`, `Ctrl+N`, `Ctrl+C`, `Esc`, `Up`/`Down` history).

### Non-Goals
- Replacing or deprecating the existing Rich CLI mode.
- Adding a web/GUI frontend.

---

## 3. Dependencies
Add to `pyproject.toml`:
```toml
"textual>=0.85.0"
```
Sync environment with `uv sync`.

---

## 4. Directory & Module Structure
```text
src/neo/
├── core/
│   ├── events.py          # UI-agnostic callback/event protocol
│   └── runner.py          # Extracted chat & tool-execution loop
└── ui/
    ├── __init__.py
    ├── app.py             # NeoTUIApp(App) entry point, bindings, layout
    ├── styles.tcss        # Textual CSS styling
    └── widgets/
        ├── __init__.py
        ├── chat_pane.py   # Scrollable message & tool-call stream
        ├── sidebar.py     # Session list, new session, token summary
        ├── input_bar.py   # Multi-line prompt input & slash-command hints
        └── modals.py      # ConfirmModal, ModelPickerModal
```

---

## 5. Core Event / Callback Contract (`src/neo/core/events.py`)
To share the LLM + tool loop between the Rich CLI and Textual TUI without duplicating logic, `runner.py` will accept a `RunnerCallbacks` protocol:

| Callback | Signature | Purpose |
| :--- | :--- | :--- |
| `on_status` | `(text: str) -> None` | Update thinking/tool-running indicator |
| `on_token` | `(chunk: str) -> None` | Stream assistant response text |
| `on_tool_call` | `(name: str, args: dict) -> None` | Display tool invocation |
| `on_tool_result` | `(name: str, result: str) -> None` | Display truncated tool output |
| `on_confirm` | `(command: str, cwd: str \| None) -> bool` | Prompt user before executing shell commands |
| `on_turn_complete` | `(query: int, completion: int, total: int, model_name: str) -> None` | Render turn token & model summary |
| `on_error` | `(message: str) -> None` | Display error banner |

- **CLI Adapter (`RichCLICallbacks`)**: Wraps `console.print` and `typer.confirm`.
- **TUI Adapter (`TextualCallbacks`)**: Bridges background worker threads to the Textual event loop via `app.call_from_thread(...)` and `threading.Event` for synchronous `on_confirm` blocking until the modal resolves.

---

## 6. UI Layout & Components
### 6.1 Screen Layout
```text
┌─────────────────────────────────────────────────────────────────────────┐
│ Header: Neo TUI  |  Session: <title>  |  Model: <current_model>         │
├──────────────────┬──────────────────────────────────────────────────────┤
│ Sidebar (Ctrl+B) │ ChatPane (VerticalScroll)                            │
│                  │                                                      │
│ [+ New Session]  │  You: ...                                            │
│                  │  Assistant: (Markdown)                               │
│ Recent Sessions: │  ▸ Tool: executeTool (collapsible)                   │
│  • Session A     │                                                      │
│  • Session B     │                                                      │
│                  │                                                      │
│ Session Tokens:  │                                                      │
│  Total: 5387     │                                                      │
├──────────────────┴──────────────────────────────────────────────────────┤
│ InputBar: Type a message or /command... (Enter to send, Shift+Enter nl) │
├─────────────────────────────────────────────────────────────────────────┤
│ Footer: Turn Tokens: Query: 0 | Completion: 0 | Session Total: 0 | ...  │
└─────────────────────────────────────────────────────────────────────────┘
```

### 6.2 Keybindings
| Key | Action |
| :--- | :--- |
| `Ctrl+B` | Toggle sidebar visibility |
| `Ctrl+N` | Create and switch to a new session |
| `Ctrl+M` | Open `ModelPickerModal` |
| `Esc` | Cancel in-flight LLM/tool turn (if running) |
| `Ctrl+Q` | Quit TUI cleanly |

### 6.3 Slash Commands in TUI
| Command | Aliases | Behavior |
| :--- | :--- | :--- |
| `/sessions` | `/session` | Open interactive Session Manager modal/pane: switch active session, **soft delete** (archive/hide), or **permanently delete** (with confirmation) |
| `/new` | `/new-session` | Create and switch to a fresh session |
| `/models` | `/model` | Open `ModelPickerModal` to switch `current_model` |
| `/compact` | — | Trigger context compaction on the active session |
| `/clear` | — | Clear the current chat pane display |
| `/help` | `/?` | Display available keybindings and slash commands |
| `/exit` | `/quit`, `/q` | Close and exit the TUI cleanly |

---

## 7. Threading & Concurrency Model
- LLM API calls and `executeTool` subprocesses run inside Textual `@work(thread=True)` workers so the UI remains responsive at 60 FPS.
- `on_confirm` blocks the worker thread on a `threading.Event` while `app.call_from_thread` pushes `ConfirmModal` onto the screen; dismissing the modal sets the boolean result and wakes the worker thread.

---

## 8. CLI Integration
In `src/neo/cli.py`:
```python
@app.command()
def tui():
    """Launch the interactive Neo TUI."""
    from neo.ui.app import NeoTUIApp
    NeoTUIApp().run()
```

---

## 9. Testing & Verification (`tests/test_tui.py`)
Using Textual's async test harness (`async with app.run_test() as pilot:`):
1. **Mount & Layout**: Verify `Header`, `Sidebar`, `ChatPane`, `InputBar`, and `Footer` mount without errors.
2. **Keybindings**: Verify `Ctrl+B` toggles sidebar and `Ctrl+N` creates a new session.
3. **Prompt Submission**: Mock the LLM runner, submit a prompt, and assert user + assistant widgets render in `ChatPane` and token footer updates.
4. **Confirmation Modal**: Trigger `on_confirm`, simulate clicking Approve/Cancel, and verify the boolean return value.

