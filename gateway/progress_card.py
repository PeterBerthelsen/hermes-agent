"""Slack progress-card rendering for gateway tool progress.

Slack renders ordinary progress crumbs as plain chat noise.  This module turns
those same accumulated tool lines into a compact status card with a high-
contrast fenced body and any clickable source links outside the fence, where
Slack mrkdwn can actually render them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

_MAX_ACTIVITY_LINES = 2
_MAX_COMMENTARY_LINES = 2
_MAX_LINE_CHARS = 180
_REPO_ROOT = Path(__file__).resolve().parents[1]
_ABSOLUTE_PATH_RE = re.compile(r"(?P<path>/(?:[^\s\"'`<>|),]+/?)+)")


@dataclass(frozen=True)
class _PathLink:
    label: str
    url: str
    short_path: str
    path: str


def _format_elapsed(seconds: float | int | None) -> str:
    """Format elapsed runtime for a small status card."""
    try:
        total = max(0, int(seconds or 0))
    except (TypeError, ValueError):
        total = 0
    minutes, secs = divmod(total, 60)
    if minutes <= 0:
        return f"{secs}s"
    return f"{minutes}m {secs:02d}s"


def _completion_time() -> str:
    # ``%-I`` is not portable to every Python platform; lstrip keeps this safe.
    return datetime.now().strftime("%I:%M %p").lstrip("0")


def _clean_whitespace(value: object) -> str:
    text = str(value or "").strip()
    return re.sub(r"\s+", " ", text)


def _truncate(text: str) -> str:
    if len(text) <= _MAX_LINE_CHARS:
        return text
    return text[: _MAX_LINE_CHARS - 1] + "…"


def _path_link_for(path_text: str) -> _PathLink | None:
    """Return a known-source link for absolute paths we can label safely."""
    path_text = path_text.rstrip(".:;!?]")
    try:
        path = Path(path_text)
        resolved = path.resolve(strict=False)
    except (OSError, RuntimeError, ValueError):
        return None

    try:
        short = resolved.relative_to(_REPO_ROOT)
    except ValueError:
        return None

    short_path = short.as_posix()
    return _PathLink(
        label="Hermes",
        url=f"file://{resolved}",
        short_path=short_path,
        path=str(resolved),
    )


def _collect_path_links(lines: Iterable[str]) -> list[_PathLink]:
    links: list[_PathLink] = []
    seen: set[str] = set()
    for line in lines:
        for match in _ABSOLUTE_PATH_RE.finditer(line):
            link = _path_link_for(match.group("path"))
            if link is None or link.path in seen:
                continue
            seen.add(link.path)
            links.append(link)
    return links


def _shorten_known_paths(text: str, links: Iterable[_PathLink]) -> str:
    shortened = text
    for link in links:
        shortened = shortened.replace(link.path, link.short_path)
    return shortened


def _clean_tool_line(line: object, *, links: Iterable[_PathLink] = ()) -> str:
    """Return a single-line activity item suitable for a fenced card body."""
    text = _clean_whitespace(line)
    if not text:
        return ""
    text = _shorten_known_paths(text, links)
    return _truncate(text)


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


def _source_line(links: list[_PathLink]) -> str | None:
    if not links:
        return None
    rendered = [f"[{link.label}]({link.url})" for link in links]
    return "Sources: " + ", ".join(rendered)


def _fenced_status(lines: list[str]) -> str:
    return "```status\n" + "\n".join(lines) + "\n```"


def render_slack_progress_card(
    lines: Iterable[object],
    elapsed_seconds: float | int | None = None,
    *,
    commentary: Iterable[object] | None = None,
    tool_count: int | None = None,
    complete: bool = False,
) -> str:
    """Render accumulated gateway progress lines as a Slack mrkdwn card.

    Links are intentionally rendered outside the fenced body because Slack does
    not render mrkdwn links inside code blocks.  The fenced body receives short
    source-relative path labels instead of long absolute paths.
    """
    raw_lines = [_clean_whitespace(line) for line in lines]
    raw_lines = [line for line in raw_lines if line]
    raw_notes = [_clean_whitespace(line) for line in (commentary or [])]
    raw_notes = [line for line in raw_notes if line]

    links = _collect_path_links([*raw_lines, *raw_notes])
    cleaned = [_clean_tool_line(line, links=links) for line in raw_lines]
    cleaned = [line for line in cleaned if line]
    notes = [_clean_tool_line(line, links=links) for line in raw_notes]
    notes = [line for line in notes if line]

    try:
        total_tools = len(cleaned) if tool_count is None else max(0, int(tool_count or 0))
    except (TypeError, ValueError):
        total_tools = len(cleaned)

    header = "*Complete*" if complete else "*Basil is working*"
    outer: list[str] = [header]
    source_line = _source_line(links)
    if source_line:
        outer.append(source_line)

    if complete:
        status_lines = [
            f"COMPLETED: {_completion_time()}",
            f"TOOLS: {total_tools}",
        ]
        if elapsed_seconds is not None:
            status_lines.append(f"ELAPSED: {_format_elapsed(elapsed_seconds)}")
        outer.append(_fenced_status(status_lines))
        return "\n".join(outer)

    phase = _infer_phase(cleaned)
    current = cleaned[-1] if cleaned else "getting oriented"
    recent = cleaned[-_MAX_ACTIVITY_LINES:]

    status_lines = [
        f"PHASE: {phase}",
        f"CURRENT: {current}",
        f"TOOLS: {total_tools}",
    ]
    if elapsed_seconds is not None:
        status_lines.append(f"ELAPSED: {_format_elapsed(elapsed_seconds)}")
    if notes:
        status_lines.append("")
        status_lines.append("NOTES:")
        for item in notes[-_MAX_COMMENTARY_LINES:]:
            status_lines.append(f"- {item}")
    if recent:
        status_lines.append("")
        status_lines.append("RECENT:")
        for item in recent:
            status_lines.append(f"- {item}")

    outer.append(_fenced_status(status_lines))
    return "\n".join(outer)
