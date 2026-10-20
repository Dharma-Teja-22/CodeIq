"""Asynchronous UI tests for CodeIq Textual App."""

from pathlib import Path
import pytest
from textual.widgets import Input, OptionList

from codeiq.tui.app import CodeIqApp
from codeiq.tui.widgets.status_bar import AppStatusBar


@pytest.mark.asyncio
async def test_codeiq_app_mount(tmp_path: Path):
    app = CodeIqApp(cwd=tmp_path, auto_approve=True)
    async with app.run_test() as pilot:
        # Check header and status bar
        status_bar = app.query_one(AppStatusBar)
        assert status_bar is not None
        assert status_bar.model == "gemini-2.5-flash"

        # Check input exists
        chat_input = app.query_one(Input)
        assert chat_input is not None

        # Check sidebar toggle
        sidebar = app.query_one("#sidebar")
        assert not sidebar.has_class("hidden")
        await pilot.press("ctrl+b")
        assert sidebar.has_class("hidden")
        await pilot.press("ctrl+b")
        assert not sidebar.has_class("hidden")


@pytest.mark.asyncio
async def test_codeiq_slash_commands(tmp_path: Path):
    app = CodeIqApp(cwd=tmp_path, auto_approve=True)
    async with app.run_test() as pilot:
        chat_input = app.query_one("#chat-input", Input)

        # Test /help command
        chat_input.value = "/help"
        await pilot.press("enter")
        await pilot.pause()

        # Test /git command
        chat_input.value = "/git"
        await pilot.press("enter")
        await pilot.pause()

        # Test /stats command
        chat_input.value = "/stats"
        await pilot.press("enter")
        await pilot.pause()

        # Test /models command
        chat_input.value = "/models"
        await pilot.press("enter")
        await pilot.pause()

        # Test /autoapprove command
        chat_input.value = "/autoapprove"
        await pilot.press("enter")
        await pilot.pause()
        assert app.config.auto_approve is False


@pytest.mark.asyncio
async def test_command_hint_panel(tmp_path: Path):
    app = CodeIqApp(cwd=tmp_path, auto_approve=True)
    async with app.run_test() as pilot:
        chat_input = app.query_one("#chat-input", Input)
        hint_panel = app.query_one("#command-hint-panel", OptionList)

        chat_input.value = "/model"
        await pilot.pause()
        prompts = [str(hint_panel.get_option_at_index(i).prompt) for i in range(hint_panel.option_count)]
        assert any("/model  |  Switch active model" in text for text in prompts)
        assert any("/models  |  List provider models" in text for text in prompts)

        chat_input.value = "hello"
        await pilot.pause()
        assert hint_panel.has_class("hidden")


@pytest.mark.asyncio
async def test_codeiq_exit_slash_command(tmp_path: Path):
    app = CodeIqApp(cwd=tmp_path, auto_approve=True)
    async with app.run_test() as pilot:
        chat_input = app.query_one("#chat-input", Input)
        chat_input.value = "/exit"
        await pilot.press("enter")
        await pilot.pause()
        assert app.is_running is False
