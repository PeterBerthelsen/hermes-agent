#!/usr/bin/env python3
"""Local-first multi-agent review ledger for Hermes development.

This script keeps private workflow state in `.agent-workflow/` so multiple
agents can share one source of truth without publishing review notes, prompts,
or pre-PR discussion to a public fork.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

WORKFLOW_DIR = Path(".agent-workflow")
BRANCHES_DIR = WORKFLOW_DIR / "branches"
REVIEWS_DIR = WORKFLOW_DIR / "reviews"
ISSUES_DIR = WORKFLOW_DIR / "issues"
LOG_PATH = WORKFLOW_DIR / "events.jsonl"
CONFIG_PATH = WORKFLOW_DIR / "config.json"

DEFAULT_CONFIG = {
    "schema_version": 1,
    "privacy": "local-private-until-explicit-push",
    "upstream_remote": "origin",
    "fork_remote": "peter",
    "upstream_repo": "NousResearch/hermes-agent",
    "fork_owner": "PeterBerthelsen",
    "base_branch": "origin/main",
    "review_policy": {
        "pre_push_reviews_required": 1,
        "required_checks": ["git diff --check", "python -m pytest"],
        "external_agent_outputs_are_private_by_default": True,
    },
}


def run(cmd: list[str], *, check: bool = True) -> str:
    result = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if check and result.returncode != 0:
        raise SystemExit(f"command failed: {' '.join(cmd)}\n{result.stderr.strip()}")
    return result.stdout.strip()


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9._/-]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value or "unnamed"


def current_branch() -> str:
    return run(["git", "branch", "--show-current"])


def git_root() -> Path:
    return Path(run(["git", "rev-parse", "--show-toplevel"]))


def ensure_repo_root() -> None:
    root = git_root()
    os.chdir(root)


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def append_event(event_type: str, payload: dict[str, Any]) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    event = {"ts": now_iso(), "type": event_type, **payload}
    with LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, sort_keys=True) + "\n")


def ensure_workflow(*, verbose: bool = False) -> None:
    for directory in (BRANCHES_DIR, REVIEWS_DIR, ISSUES_DIR):
        directory.mkdir(parents=True, exist_ok=True)
    if not CONFIG_PATH.exists():
        write_json(CONFIG_PATH, DEFAULT_CONFIG)
    readme = WORKFLOW_DIR / "README.md"
    if not readme.exists():
        readme.write_text(
            "# Private Agent Workflow Ledger\n\n"
            "This directory is intentionally gitignored. It is the local source of truth for "
            "multi-agent Hermes work before a branch is pushed to Peter's fork or opened as "
            "an upstream PR.\n\n"
            "Tracked here:\n"
            "- branch records\n"
            "- local issue/task records\n"
            "- external-agent review reports\n"
            "- PR handoff summaries\n\n"
            "Do not put API keys or secrets here. Treat it as private project metadata, not a "
            "secret store.\n",
            encoding="utf-8",
        )
    if verbose:
        append_event("init", {"workflow_dir": str(WORKFLOW_DIR)})
        print(f"initialized {WORKFLOW_DIR}")


def init(_: argparse.Namespace) -> None:
    ensure_workflow(verbose=True)


def branch_record_path(branch: str) -> Path:
    return BRANCHES_DIR / f"{slugify(branch).replace('/', '__')}.json"


def start(args: argparse.Namespace) -> None:
    ensure_workflow()
    branch = args.branch or current_branch()
    base = args.base or DEFAULT_CONFIG["base_branch"]
    head = run(["git", "rev-parse", "HEAD"])
    path = branch_record_path(branch)
    if path.exists() and not args.update:
        raise SystemExit(f"branch record already exists: {path} (use --update)")
    record = load_json(path, {})
    record.update(
        {
            "schema_version": 1,
            "branch": branch,
            "base": base,
            "title": args.title,
            "status": record.get("status", "local"),
            "created_at": record.get("created_at", now_iso()),
            "updated_at": now_iso(),
            "created_from_sha": record.get("created_from_sha", head),
            "owner_agent": args.agent,
            "summary": args.summary or "",
            "linked_issues": args.issue or [],
            "reviews": record.get("reviews", []),
            "tests": record.get("tests", []),
            "pr": record.get("pr"),
        }
    )
    write_json(path, record)
    append_event("branch_start", {"branch": branch, "path": str(path), "agent": args.agent})
    print(path)


def record_review(args: argparse.Namespace) -> None:
    ensure_workflow()
    branch = args.branch or current_branch()
    agent = slugify(args.agent)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    review_path = REVIEWS_DIR / slugify(branch).replace("/", "__") / f"{stamp}-{agent}.md"
    review_path.parent.mkdir(parents=True, exist_ok=True)
    if args.file:
        body = Path(args.file).read_text(encoding="utf-8")
    else:
        body = sys.stdin.read()
    header = (
        f"# Agent Review: {branch}\n\n"
        f"- Agent: {args.agent}\n"
        f"- Timestamp: {now_iso()}\n"
        f"- Base: {args.base or DEFAULT_CONFIG['base_branch']}\n"
        f"- Verdict: {args.verdict}\n\n"
    )
    review_path.write_text(header + body.strip() + "\n", encoding="utf-8")

    branch_path = branch_record_path(branch)
    record = load_json(branch_path, {"branch": branch, "base": args.base or DEFAULT_CONFIG["base_branch"], "reviews": [], "tests": []})
    record.setdefault("reviews", []).append(
        {
            "agent": args.agent,
            "verdict": args.verdict,
            "path": str(review_path),
            "recorded_at": now_iso(),
        }
    )
    record["updated_at"] = now_iso()
    write_json(branch_path, record)
    append_event("review_recorded", {"branch": branch, "agent": args.agent, "verdict": args.verdict, "path": str(review_path)})
    print(review_path)


def record_test(args: argparse.Namespace) -> None:
    ensure_workflow()
    branch = args.branch or current_branch()
    branch_path = branch_record_path(branch)
    record = load_json(branch_path, {"branch": branch, "reviews": [], "tests": []})
    record.setdefault("tests", []).append(
        {
            "command": args.command,
            "result": args.result,
            "recorded_at": now_iso(),
            "notes": args.notes or "",
        }
    )
    record["updated_at"] = now_iso()
    write_json(branch_path, record)
    append_event("test_recorded", {"branch": branch, "command": args.command, "result": args.result})
    print(branch_path)


def status(args: argparse.Namespace) -> None:
    ensure_workflow()
    branch = args.branch or current_branch()
    record = load_json(branch_record_path(branch), None)
    diff_stat = run(["git", "diff", f"{args.base or DEFAULT_CONFIG['base_branch']}...HEAD", "--stat"], check=False)
    out = {
        "branch": branch,
        "record": record,
        "git": {
            "head": run(["git", "rev-parse", "--short", "HEAD"], check=False),
            "working_tree": run(["git", "status", "--short"], check=False).splitlines(),
            "diff_stat": diff_stat.splitlines(),
        },
    }
    print(json.dumps(out, indent=2, sort_keys=True))


def pr_body(args: argparse.Namespace) -> None:
    ensure_workflow()
    branch = args.branch or current_branch()
    record = load_json(branch_record_path(branch), {})
    base = record.get("base") or args.base or DEFAULT_CONFIG["base_branch"]
    changed = run(["git", "diff", f"{base}...HEAD", "--stat"], check=False)
    commits = run(["git", "log", f"{base}..HEAD", "--oneline"], check=False)
    reviews = record.get("reviews", [])
    tests = record.get("tests", [])

    print("## Summary")
    print(record.get("summary") or "- See branch commits and diff.")
    print("\n## Local Agent Review")
    if reviews:
        for review in reviews:
            print(f"- {review['agent']}: {review['verdict']} (`{review['path']}`)")
    else:
        print("- No local agent reviews recorded.")
    print("\n## Tests / Checks")
    if tests:
        for test in tests:
            notes = f" — {test['notes']}" if test.get("notes") else ""
            print(f"- `{test['command']}`: {test['result']}{notes}")
    else:
        print("- Not recorded yet.")
    print("\n## Commits")
    print("```text")
    print(commits or "No commits relative to base.")
    print("```")
    print("\n## Diff Stat")
    print("```text")
    print(changed or "No diff relative to base.")
    print("```")
    if record.get("linked_issues"):
        print("\n## Linked Issues")
        for issue in record["linked_issues"]:
            print(f"- {issue}")


def create_issue(args: argparse.Namespace) -> None:
    ensure_workflow()
    issue_id = args.id or dt.datetime.now(dt.timezone.utc).strftime("local-%Y%m%d-%H%M%S")
    path = ISSUES_DIR / f"{slugify(issue_id)}.json"
    record = {
        "schema_version": 1,
        "id": issue_id,
        "title": args.title,
        "status": "open",
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "owner_agent": args.agent,
        "body": args.body or "",
        "github_issue": args.github_issue,
        "branches": args.branch or [],
    }
    write_json(path, record)
    append_event("issue_created", {"id": issue_id, "path": str(path), "agent": args.agent})
    print(path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(required=True)

    p = sub.add_parser("init", help="create the private workflow ledger")
    p.set_defaults(func=init)

    p = sub.add_parser("start", help="create/update a branch record")
    p.add_argument("--branch")
    p.add_argument("--base")
    p.add_argument("--title", required=True)
    p.add_argument("--summary")
    p.add_argument("--agent", default="Basil")
    p.add_argument("--issue", action="append")
    p.add_argument("--update", action="store_true")
    p.set_defaults(func=start)

    p = sub.add_parser("review", help="record an external-agent review report")
    p.add_argument("--branch")
    p.add_argument("--base")
    p.add_argument("--agent", required=True)
    p.add_argument("--verdict", choices=["approved", "commented", "changes-requested", "failed"], default="commented")
    p.add_argument("--file")
    p.set_defaults(func=record_review)

    p = sub.add_parser("test", help="record a local test/check result")
    p.add_argument("--branch")
    p.add_argument("--command", required=True)
    p.add_argument("--result", choices=["pass", "fail", "skip"], required=True)
    p.add_argument("--notes")
    p.set_defaults(func=record_test)

    p = sub.add_parser("issue", help="create a local issue/task record")
    p.add_argument("--id")
    p.add_argument("--title", required=True)
    p.add_argument("--body")
    p.add_argument("--agent", default="Basil")
    p.add_argument("--github-issue")
    p.add_argument("--branch", action="append")
    p.set_defaults(func=create_issue)

    p = sub.add_parser("status", help="show branch record plus git status as JSON")
    p.add_argument("--branch")
    p.add_argument("--base")
    p.set_defaults(func=status)

    p = sub.add_parser("pr-body", help="render a PR body from local records")
    p.add_argument("--branch")
    p.add_argument("--base")
    p.set_defaults(func=pr_body)

    return parser


def main() -> None:
    ensure_repo_root()
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
