"""Command Line Interface for CodeIq."""

from __future__ import annotations
import argparse
import os
from pathlib import Path
import sys

from . import __version__
from .config import Config
from .storage.session_store import SessionStore
from .tui.app import CodeIqApp


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="codeiq",
        description="CodeIq: An OpenCode-like AI coding assistant that runs entirely in your terminal.",
    )
    parser.add_argument(
        "--dir", "-d",
        type=str,
        default=os.getcwd(),
        help="Target project directory (default: current working directory)",
    )
    parser.add_argument(
        "--model", "-m",
        type=str,
        default=None,
        help="LLM model to use (default: gemini-2.5-flash)",
    )
    parser.add_argument(
        "--provider", "-p",
        type=str,
        default=None,
        choices=["gemini", "openai", "groq", "ollama"],
        help="LLM provider (default: gemini)",
    )
    parser.add_argument(
        "--api-key", "-k",
        type=str,
        default=None,
        help="API key for selected provider (or set GEMINI_API_KEY/OPENAI_API_KEY env)",
    )
    parser.add_argument(
        "--resume", "-r",
        type=str,
        default=None,
        help="Resume an existing session by ID",
    )
    parser.add_argument(
        "--auto-approve", "-y",
        action="store_true",
        help="Automatically approve file writes and terminal commands without interactive prompt",
    )
    parser.add_argument(
        "--list-sessions",
        action="store_true",
        help="List all saved sessions in current project and exit",
    )
    parser.add_argument(
        "--export-session",
        type=str,
        default=None,
        help="Export specified session ID to markdown and exit",
    )
    parser.add_argument(
        "--version", "-v",
        action="version",
        version=f"CodeIq v{__version__}",
    )

    args = parser.parse_args()

    target_dir = Path(args.dir).resolve()
    if not target_dir.exists() or not target_dir.is_dir():
        print(f"Error: Target directory '{target_dir}' does not exist.", file=sys.stderr)
        sys.exit(1)

    store = SessionStore(cwd=str(target_dir))

    # Handle --list-sessions
    if args.list_sessions:
        sessions = store.list_sessions()
        if not sessions:
            print(f"No stored sessions found in '{target_dir}'.")
            return
        print(f"\nSaved Sessions in '{target_dir}':")
        print("-" * 80)
        for s in sessions:
            cost_str = f"${s['cost']:.4f}" if s.get("cost") else "$0.00"
            print(f"ID:      {s['id']}")
            print(f"Title:   {s['title']}")
            print(f"Model:   {s['model']} ({s['provider']})")
            print(f"Tokens:  {s['total_tokens']:,} ({cost_str})")
            print(f"Updated: {s['updated_at']}")
            print("-" * 80)
        return

    # Handle --export-session
    if args.export_session:
        session = store.load_session(args.export_session)
        if not session:
            print(f"Error: Session '{args.export_session}' not found.", file=sys.stderr)
            sys.exit(1)
        out_path = store.export_markdown(session)
        print(f"Exported session '{args.export_session}' to: {out_path}")
        return

    # Configure API key if passed via CLI
    if args.api_key:
        if args.provider == "openai":
            os.environ["OPENAI_API_KEY"] = args.api_key
        else:
            os.environ["GEMINI_API_KEY"] = args.api_key

    # Launch Textual TUI
    app = CodeIqApp(
        cwd=target_dir,
        model=args.model,
        provider=args.provider,
        session_id=args.resume,
        auto_approve=args.auto_approve,
    )
    app.run()


if __name__ == "__main__":
    main()
