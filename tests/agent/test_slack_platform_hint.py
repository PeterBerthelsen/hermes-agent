"""Tests for Slack communication guidance."""

from agent.prompt_builder import PLATFORM_HINTS


def test_slack_hint_includes_conversation_buffer_and_autonomous_cues():
    hint = PLATFORM_HINTS["slack"]

    assert "conversational by default" in hint
    assert "ask the smallest useful follow-up question" in hint
    assert "boil the ocean" in hint
    assert "I'm walking away" in hint
    assert "EOD" in hint
    assert "public progress commentary" in hint
    assert "do not expose hidden chain-of-thought" in hint
