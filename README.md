# CodeIQ

CodeIQ is an AI-powered developer CLI toolkit designed to accelerate your development workflows. It streamlines daily software development tasks by bringing intelligent assistance and Git automation directly to your terminal.

## Key Features

- **Interactive AI Chat & Multi-Turn Sessions**: Ask technical questions, edit code, execute commands, and maintain conversation context across sessions.
- **Session Management**: Persistent JSON sessions stored cleanly in `~/.codeiq/sessions/`, with commands to list, resume, or close sessions.
- **AI-Powered Conventional Commits**: Automatically analyze staged git changes to generate standardized, descriptive conventional commit messages.
- **Git & File Operations Support**: Perform essential Git actions, file reads/edits, web searches, and command executions seamlessly with terminal status indicators.

---

## Getting Started Locally

Follow the steps below to set up and run the project locally.

### 1. Clone or Pull the Repository

If you are setting it up for the first time, clone the repository:

```bash
git clone <repo-url>
cd CodeIq
```

If you already have the repository locally and want the latest changes, pull updates:

```bash
git pull origin main
```

---

### 2. Set Up a Virtual Environment

Create and activate an isolated virtual environment:

- **macOS / Linux**:
  ```bash
  python -m venv .venv
  source .venv/bin/activate
  ```

- **Windows (PowerShell)**:
  ```powershell
  python -m venv .venv
  .venv\Scripts\Activate.ps1
  ```

- **Windows (Command Prompt)**:
  ```cmd
  python -m venv .venv
  .venv\Scripts\activate.bat
  ```

---

### 3. Install Dependencies

Install the project in editable development mode:

```bash
pip install -e .
```

---

### 4. Configure Environment Variables

Create your environment configuration file (`.env`) and provide your Gemini API key:

```env
GEMINI_API_KEY=your_gemini_api_key_here
```

---

## CLI Usage

Once installed, use the CLI commands directly in your terminal:

### 1. AI Chat & Session Management

CodeIQ automatically persists conversations in JSON format under `~/.codeiq/sessions/` (`C:\Users\<username>\.codeiq\sessions\` on Windows), keeping your repository clean.

- **Start a new chat session**:
  ```bash
  codeiq chat
  ```

- **Resume the latest chat session**:
  ```bash
  codeiq chat --resume
  # or short flag:
  codeiq chat -r
  ```

- **Resume a specific session (by session ID or prefix)**:
  ```bash
  codeiq chat --session <session_id>
  # or short flag:
  codeiq chat -s "CodeIq_Dev-Auto Compaction Not Triggering"
  ```

- **List all saved sessions** (renders a clean list with only session ID and status):
  ```bash
  codeiq sessions
  ```
  *Output example:*
  ```text
  Sessions (C:\Users\<username>\.codeiq\sessions):

  • CodeIq_Dev-Auto Compaction Not Triggering [active]
  • CodeIq_Dev-Fix Database Migration [closed]
  ```

- **Soft delete a session** (prevents listing and reopening):
  ```bash
  codeiq sessions --delete <session_id>
  # or short flag:
  codeiq sessions -d <session_id>
  ```

- **Permanently purge soft-deleted sessions**:
  ```bash
  # Purge all soft-deleted sessions at once
  codeiq sessions --purge all

  # Or purge a single soft-deleted session by ID or prefix
  codeiq sessions --purge <session_id>
  ```

- **Restore a soft-deleted session**:
  ```bash
  codeiq sessions --restore <session_id>
  ```

- **Include soft-deleted sessions in the list**:
  ```bash
  codeiq sessions --show-deleted
  ```

- **Close a session from CLI** (marks status as closed without deleting):
  ```bash
  codeiq sessions --close <session_id>
  # or short flag:
  codeiq sessions -c <session_id>
  ```

- **In-Chat Commands**:
  - `exit`, `quit`, or `bye`: Leaves the session in an `active` state so you can resume it later.
  - `close` or `close session`: Marks the current session as `closed` and exits.
  - `delete` or `delete session`: Soft-deletes the current session immediately and exits.

---

### 2. One-Off AI Queries & Model Selection

- **One-off AI prompt**:
  ```bash
  codeiq generate-response "How do I optimize a SQL query?"
  ```

- **Select or configure AI models**:
  ```bash
  # Interactive arrow-key model selector
  codeiq models

  # Add a new model to config
  codeiq models --add <model_name>
  ```

---

### 3. Git Operations

- **Stage files**:
  ```bash
  codeiq add .
  ```

- **Generate an AI commit message and commit**:
  ```bash
  codeiq commit
  ```

- **Perform Git operations**:
  ```bash
  codeiq git --type push
  codeiq git --type pull
  codeiq git --type branch
  ```
