"""Autonomous agent reasoning and execution loop for CodeIq."""

from __future__ import annotations
import asyncio
from pathlib import Path
from typing import Any, Callable, Coroutine, Dict, List, Optional

from ..config import Config
from ..llm.base import BaseLLMProvider, StreamChunk
from ..llm.factory import create_llm_provider
from ..models import ChatMessage, Role, Session, ToolCall, ToolState, TokenUsage
from ..storage.session_store import SessionStore
from ..tools.registry import ToolRegistry
from .context import ContextManager
from .prompts import build_system_prompt


class CodeIqAgent:
    """Manages multi-turn conversations and autonomous tool-calling loops."""

    def __init__(
        self,
        session: Session,
        config: Optional[Config] = None,
        tool_registry: Optional[ToolRegistry] = None,
        session_store: Optional[SessionStore] = None,
    ):
        self.session = session
        self.config = config or Config(cwd=session.cwd)
        self.cwd = Path(session.cwd).resolve()
        self.tools = tool_registry or ToolRegistry(cwd=self.cwd)
        self.session_store = session_store or SessionStore(cwd=self.cwd)
        self.context_mgr = ContextManager(cwd=self.cwd)
        self.llm: BaseLLMProvider = create_llm_provider(
            provider_name=session.provider,
            model_name=session.model,
            config=self.config,
        )

    def switch_model(self, provider: str, model: str) -> None:
        self.session.provider = provider
        self.session.model = model
        self.llm = create_llm_provider(
            provider_name=provider,
            model_name=model,
            config=self.config,
        )
        self.session_store.save_session(self.session)

    async def run_turn(
        self,
        user_input: str,
        on_text_delta: Optional[Callable[[str], None]] = None,
        on_thought_delta: Optional[Callable[[str], None]] = None,
        on_tool_call_detected: Optional[Callable[[ToolCall], None]] = None,
        on_tool_approved: Optional[Callable[[ToolCall], Coroutine[Any, Any, bool]]] = None,
        on_tool_finished: Optional[Callable[[ToolCall], None]] = None,
    ) -> None:
        """Executes a complete agent turn, recursively dispatching tools until completion."""
        # 1. Resolve @file mentions and enrich user input
        enriched_text, attached_files = self.context_mgr.resolve_mentions_and_enrich_prompt(user_input)

        user_msg = ChatMessage(
            role=Role.USER,
            content=enriched_text,
        )
        self.session.messages.append(user_msg)

        # 2. Prepare tools schema according to provider
        provider_name = self.session.provider.lower()
        if provider_name in ("gemini", "google"):
            tools_schema = self.tools.to_gemini_tools()
        else:
            tools_schema = self.tools.to_openai_tools()

        # 3. Autonomous loop
        step = 0
        max_steps = self.config.max_steps

        while step < max_steps:
            step += 1
            project_overview = self.context_mgr.generate_project_overview()
            system_prompt = build_system_prompt(self.cwd, project_overview)

            accumulated_text = ""
            accumulated_thought = ""
            pending_tool_calls: List[ToolCall] = []
            turn_usage: Optional[TokenUsage] = None

            async for chunk in self.llm.stream_chat(
                messages=self.session.messages,
                tools=tools_schema,
                system_prompt=system_prompt,
                temperature=self.config.temperature,
            ):
                if chunk.text_delta:
                    accumulated_text += chunk.text_delta
                    if on_text_delta:
                        on_text_delta(chunk.text_delta)

                if chunk.thought_delta:
                    accumulated_thought += chunk.thought_delta
                    if on_thought_delta:
                        on_thought_delta(chunk.thought_delta)

                if chunk.tool_calls:
                    pending_tool_calls.extend(chunk.tool_calls)
                    for tc in chunk.tool_calls:
                        if on_tool_call_detected:
                            on_tool_call_detected(tc)

                if chunk.token_usage:
                    turn_usage = chunk.token_usage

            # Update session total tokens
            if turn_usage:
                self.session.total_tokens.add(turn_usage)

            # Check if tools were proposed
            if not pending_tool_calls:
                # Normal final response
                assistant_msg = ChatMessage(
                    role=Role.ASSISTANT,
                    content=accumulated_text,
                    thought=accumulated_thought if accumulated_thought else None,
                    token_usage=turn_usage,
                )
                self.session.messages.append(assistant_msg)
                break

            # Assistant called tools
            assistant_msg = ChatMessage(
                role=Role.ASSISTANT,
                content=accumulated_text,
                thought=accumulated_thought if accumulated_thought else None,
                tool_calls=pending_tool_calls,
                token_usage=turn_usage,
            )
            self.session.messages.append(assistant_msg)

            # Process each tool call
            for tc in pending_tool_calls:
                # Check for diff preview
                tc.diff_preview = self.tools.generate_diff_preview(tc.name, tc.args)

                # Check if approval needed
                needs_approval = self.tools.is_approval_needed(
                    name=tc.name,
                    args=tc.args,
                    auto_approve=self.config.auto_approve,
                )

                approved = True
                if needs_approval and on_tool_approved:
                    tc.state = ToolState.PENDING_APPROVAL
                    approved = await on_tool_approved(tc)

                if approved:
                    tc.state = ToolState.RUNNING
                    loop = asyncio.get_running_loop()
                    try:
                        result_str = await loop.run_in_executor(None, self.tools.execute, tc.name, tc.args)
                        tc.result = result_str
                        tc.state = ToolState.SUCCESS
                    except Exception as e:
                        tc.error = str(e)
                        tc.state = ToolState.ERROR
                else:
                    tc.state = ToolState.REJECTED
                    tc.error = "Operation was rejected by the user."

                if on_tool_finished:
                    on_tool_finished(tc)

            # Append tool responses message to history
            tool_msg = ChatMessage(
                role=Role.TOOL,
                content="",
                tool_calls=pending_tool_calls,
            )
            self.session.messages.append(tool_msg)

            # Save session progress
            self.session_store.save_session(self.session)

        # Final save
        self.session_store.save_session(self.session)
