"""Tests for Slack-style gateway progress cards."""

from gateway.progress_card import render_slack_progress_card


def test_progress_card_renders_current_phase_and_recent_activity():
    card = render_slack_progress_card(
        [
            "🔍 search_files: \"progress_card\"",
            "📖 read_file: \"gateway/run.py\"",
            "✏️ patch...",
        ],
        elapsed_seconds=65,
    )

    assert "*Basil is working*" in card
    assert "Phase: `editing`" in card
    assert "Current: ✏️ patch..." in card
    assert "Elapsed: 1m 05s" in card
    assert "Recent activity:" in card
    assert "search_files" not in card
    assert "read_file" in card


def test_progress_card_renders_total_tool_count_and_public_commentary():
    card = render_slack_progress_card(
        ["🔍 search_files: \"progress_card\""],
        elapsed_seconds=9,
        commentary=[
            "I’m checking the existing gateway hooks first.",
            "Found the Slack edit path; wiring the card there.",
        ],
        tool_count=4,
    )

    assert "Tool calls: 4" in card
    assert "Notes:" in card
    assert "existing gateway hooks" in card
    assert "Slack edit path" in card


def test_progress_card_infers_testing_phase():
    card = render_slack_progress_card(["⚙️ terminal: \"python -m pytest tests/gateway\""], elapsed_seconds=4)

    assert "Phase: `testing`" in card
    assert "Elapsed: 4s" in card


def test_progress_card_limits_recent_activity_to_two_items():
    card = render_slack_progress_card([f"tool {i}" for i in range(12)])

    assert "tool 9" not in card
    assert "tool 10" in card
    assert "tool 11" in card


def test_progress_card_limits_commentary_to_two_recent_public_notes():
    card = render_slack_progress_card(
        ["⚙️ terminal..."],
        commentary=[f"note {i}" for i in range(5)],
    )

    assert "note 2" not in card
    assert "note 3" in card
    assert "note 4" in card


def test_progress_card_can_render_complete_summary_without_recent_details():
    card = render_slack_progress_card(
        ["🔍 search_files: \"progress_card\"", "⚙️ terminal: \"pytest\""],
        elapsed_seconds=125,
        commentary=["Checking the card", "Running tests"],
        tool_count=8,
        complete=True,
    )

    assert "*Complete*" in card
    assert "Basil is working" not in card
    assert "Phase:" not in card
    assert "Current:" not in card
    assert "Notes:" not in card
    assert "Recent activity:" not in card
    assert "Tool calls: 8" in card
    assert "Completed:" in card
    assert "Elapsed: 2m 05s" in card
