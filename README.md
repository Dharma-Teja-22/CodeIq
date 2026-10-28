# CodeIQ

CodeIQ is an AI-powered developer CLI toolkit designed to accelerate your development workflows. It streamlines daily software development tasks by bringing intelligent assistance and Git automation directly to your terminal.

## Key Features

- **Interactive AI Chat & One-off Queries**: Ask technical questions, debug logic, and receive intelligent suggestions in real-time right inside your console.
- **AI-Powered Conventional Commits**: Automatically analyze staged git changes to generate standardized, descriptive conventional commit messages.
- **Git Operations Support**: Perform essential Git actions seamlessly with rich terminal status indicators and clean formatted output.

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

Create your environment configuration file and provide your Gemini API key:

```env
GEMINI_API_KEY=your_gemini_api_key_here
```

---

## Usage

Once installed, use the CLI commands directly in your terminal:

- **One-off AI query**:
  ```bash
  codeiq generate-response "How do I optimize a SQL query?"
  ```

- **Interactive AI chat**:
  ```bash
  codeiq chat
  ```

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
