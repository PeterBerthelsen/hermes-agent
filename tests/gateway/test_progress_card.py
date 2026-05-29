"""Tests for Slack-style gateway progress cards."""

from pathlib import Path

from gateway.progress_card import render_slack_progress_card


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_progress_card_renders_current_phase_in_status_fence():
    card = render_slack_progress_card(
        [
            '🔍 search_files: "progress_card"',
            '📖 read_file: "gateway/run.py"',
            '✏️ patch...',
        ],
        elapsed_seconds=65,
    )

    assert card.startswith("*Basil is working*")
    assert "```status\n" in card
    assert "PHASE: editing" in card
    assert "CURRENT: ✏️ patch..." in card
    assert "ELAPSED: 1m 05s" in card
    assert "RECENT:" in card
    assert "search_files" not in card
    assert "read_file" in card
    assert "Phase: `editing`" not in card


def test_progress_card_renders_total_tool_count_and_public_commentary():
    card = render_slack_progress_card(
        ['🔍 search_files: "progress_card"'],
        elapsed_seconds=9,
        commentary=[
            "I’m checking the existing gateway hooks first.",
            "Found the Slack edit path; wiring the card there.",
        ],
        tool_count=4,
    )

    assert "TOOLS: 4" in card
    assert "NOTES:" in card
    assert "existing gateway hooks" in card
    assert "Slack edit path" in card


def test_progress_card_links_known_hermes_paths_without_inline_code_noise():
    path = REPO_ROOT / "gateway" / "run.py"
    card = render_slack_progress_card(
        [f'📖 read_file: "{path}"'],
        elapsed_seconds=4,
    )

    assert f"[Hermes](file://{path})" in card
    assert f"`{path}`" not in card
    # Keep the clickable source link outside the status fence; Slack does not
    # render mrkdwn links inside code blocks.
    link_section, fence_section = card.split("```status", 1)
    assert "[Hermes](file://" in link_section
    assert "[Hermes](file://" not in fence_section
    # The high-contrast body should use a short path label, not a long absolute
    # path that overwhelms the card.
    assert "gateway/run.py" in fence_section
    assert str(path) not in fence_section


def test_progress_card_infers_testing_phase():
    card = render_slack_progress_card(
        ['⚙️ terminal: "python -m pytest tests/gateway"'],
        elapsed_seconds=4,
    )

    assert "PHASE: testing" in card
    assert "ELAPSED: 4s" in card


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


def test_progress_card_can_render_complete_summary_as_status_fence():
    card = render_slack_progress_card(
        ['🔍 search_files: "progress_card"', '⚙️ terminal: "pytest"'],
        elapsed_seconds=125,
        commentary=["Checking the card", "Running tests"],
        tool_count=8,
        complete=True,
    )

    assert card.startswith("*Complete*")
    assert "```status\n" in card
    assert "Basil is working" not in card
    assert "PHASE:" not in card
    assert "CURRENT:" not in card
    assert "NOTES:" not in card
    assert "RECENT:" not in card
    assert "TOOLS: 8" in card
    assert "COMPLETED:" in card
    assert "ELAPSED: 2m 05s" in card
