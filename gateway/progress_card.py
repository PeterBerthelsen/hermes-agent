"""Compact progress-card rendering for chat gateways.

The normal gateway progress renderer accumulates tool lines and edits a single
message. That is functional, but in Slack it reads like raw terminal crumbs.
This module renders the same data as a small agent-status card: current phase,
elapsed time, and recent activity.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Iterable


_MAX_ACTIVITY_LINES = 2
_MAX_COMMENTARY_LINES = 2


def _clean_tool_line(line: object) -> str:
    """Return a Slack-friendly single-line activity item."""
    text = str(line or "").strip()
    text = re.sub(r"\s+", " ", text)
    return text[:180] + "…" if len(text) > 181 else text


def _infer_phase(lines: list[str]) -> str:
    """Infer a human phase label from the most recent tool/activity line."""
    if not lines:
        return "starting"

    latest = lines[-1].lower()
    if any(token in latest for token in ("pytest", "test", "vitest", "jest", "playwright")):
        return "testing"
    if any(token in latest for token in ("patch", "write_file", "edit", "apply_patch")):
        return "editing"
    if any(token in latest for token in ("read_file", "search_files", "browser", "web", "grep", "inspect")):
        return "inspecting"
    if any(token in latest for token in ("terminal", "execute_code", "process")):
        return "running commands"
    return "working"


def _format_elapsed(seconds: float | int | None) -> str:
    try:
        total = max(0, int(seconds or 0))
    except (TypeError, ValueError):
        total = 0
    minutes, secs = divmod(total, 60)
    if minutes <= 0:
        return f"{secs}s"
    return f"{minutes}m {secs:02d}s"


def render_slack_progress_card(
    lines: Iterable[object],
    *,
    elapsed_seconds: float | int | None = None,
    commentary: Iterable[object] | None = None,
    tool_count: int | None = None,
    complete: bool = False,
) -> str:
    """Render accumulated progress lines as an editable Slack status card.

    Parameters
    ----------
    lines:
        Tool/activity lines already produced by gateway progress callbacks.
    elapsed_seconds:
        Runtime for display. If omitted, the card still renders deterministically.
    commentary:
        Optional public assistant status notes. These are not chain-of-thought;
        they are short user-facing process updates emitted by the agent.
    tool_count:
        Total tool calls seen so far. Defaults to the number of activity lines.
    complete:
        Render the finished-state card. Finished cards intentionally omit
        transient notes/activity so they read as a small completion marker.
    """
    cleaned = [_clean_tool_line(line) for line in lines if _clean_tool_line(line)]
    notes = [_clean_tool_line(line) for line in (commentary or []) if _clean_tool_line(line)]
    total_tools = len(cleaned) if tool_count is None else max(0, int(tool_count or 0))

    if complete:
        body = [
            "*Complete*",
            f"• Completed: {datetime.now().strftime('%-I:%M %p')}",
            f"• Tool calls: {total_tools}",
        ]
        if elapsed_seconds is not None:
            body.append(f"• Elapsed: {_format_elapsed(elapsed_seconds)}")
        return "\n".join(body)

    phase = _infer_phase(cleaned)
    current = cleaned[-1] if cleaned else "getting oriented"
    recent = cleaned[-_MAX_ACTIVITY_LINES:]

    body = [
        "*Basil is working*",
        f"• Phase: `{phase}`",
        f"• Current: {current}",
        f"• Tool calls: {total_tools}",
    ]
    if elapsed_seconds is not None:
        body.append(f"• Elapsed: {_format_elapsed(elapsed_seconds)}")
    if notes:
        body.append("• Notes:")
        for item in notes[-_MAX_COMMENTARY_LINES:]:
            body.append(f"  ◦ {item}")
    if recent:
        body.append("• Recent activity:")
        for item in recent:
            body.append(f"  ◦ {item}")
    return "\n".join(body)
