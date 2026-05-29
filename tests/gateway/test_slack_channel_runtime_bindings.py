"""Tests for Slack channel_runtime_bindings resolution."""

from gateway.config import Platform
from gateway.platforms.base import (
    MessageEvent,
    MessageType,
    resolve_channel_runtime_binding,
)
from gateway.session import SessionSource


def test_resolve_channel_runtime_exact_match():
    config_extra = {
        "channel_runtime_bindings": [
            {"id": "*", "model": "gpt-5.5", "reasoning_effort": "high"},
            {
                "id": "C0CODE",
                "provider": "openai-codex",
                "model": "gpt-5.4-mini",
                "reasoning_effort": "low",
                "prompt": "Quick answers.",
            },
        ]
    }

    assert resolve_channel_runtime_binding(config_extra, "C0CODE") == {
        "provider": "openai-codex",
        "model": "gpt-5.4-mini",
        "reasoning_effort": "low",
        "prompt": "Quick answers.",
    }


def test_resolve_channel_runtime_default_binding():
    config_extra = {
        "channel_runtime_bindings": [
            {
                "id": "*",
                "default": True,
                "provider": "openai-codex",
                "model": "gpt-5.5",
                "reasoning_effort": "high",
                "prompt": "Onboard this channel.",
            },
        ]
    }

    assert resolve_channel_runtime_binding(config_extra, "C0NEW") == {
        "provider": "openai-codex",
        "model": "gpt-5.5",
        "reasoning_effort": "high",
        "prompt": "Onboard this channel.",
    }


def test_resolve_channel_runtime_parent_match():
    config_extra = {
        "channel_runtime_bindings": [
            {"id": "C0PARENT", "model": "gpt-5.5", "reasoning_effort": "xhigh"},
        ]
    }

    assert resolve_channel_runtime_binding(
        config_extra,
        "thread-ts-123",
        parent_id="C0PARENT",
    ) == {
        "model": "gpt-5.5",
        "reasoning_effort": "xhigh",
    }


def test_resolve_channel_runtime_system_prompt_alias_and_personality():
    config_extra = {
        "channel_runtime_bindings": [
            {
                "ids": ["C0A", "C0B"],
                "system_prompt": "Alias prompt.",
                "personality": "technical",
                "model": "  gpt-5.5  ",
            },
        ]
    }

    assert resolve_channel_runtime_binding(config_extra, "C0B") == {
        "model": "gpt-5.5",
        "prompt": "Alias prompt.",
        "personality": "technical",
    }


def test_message_event_carries_channel_runtime():
    runtime = {"model": "gpt-5.5", "reasoning_effort": "high"}
    source = SessionSource(
        platform=Platform.SLACK,
        chat_id="C0CODE",
        chat_name="coding",
        chat_type="group",
        user_id="U0ABC",
        user_name="Peter",
    )
    event = MessageEvent(
        text="work",
        message_type=MessageType.TEXT,
        source=source,
        raw_message={},
        message_id="123.456",
        channel_runtime=runtime,
    )

    assert event.channel_runtime == runtime
