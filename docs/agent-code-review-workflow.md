# Local-First Agent Code Review Workflow

This repository can support multiple coding/review agents while keeping pre-PR work private. The shared local source of truth is `.agent-workflow/`, managed by `scripts/agent_review_workflow.py`.

`.agent-workflow/` is intentionally gitignored. It records branch metadata, local issues, test results, and external-agent review reports before anything is pushed to Peter's public fork.

## Privacy Boundary

| Phase | Location | Visibility |
| --- | --- | --- |
| Local branch/worktree | git checkout on this machine | private to this machine |
| Agent review report | `.agent-workflow/reviews/` | private to this machine |
| Local issue/task record | `.agent-workflow/issues/` | private to this machine |
| Fork branch | `PeterBerthelsen/hermes-agent` | public, because the fork is public |
| Upstream PR | `NousResearch/hermes-agent` | public |

Do not push a branch until the local record is clean enough to become public.

## Source of Truth

Use the ledger for coordination between Basil, Codex, Claude Code, GPT Code Review, or any other agent:

```bash
python scripts/agent_review_workflow.py init
python scripts/agent_review_workflow.py start \
  --title "fix: concise description" \
  --summary "What this branch is intended to change" \
  --agent Basil
```

The branch record lives at:

```text
.agent-workflow/branches/<branch>.json
```

Every review or test result appends to that record and to `.agent-workflow/events.jsonl`.

## Normal Branch Flow

1. Start from a clean worktree or an isolated worktree.

   ```bash
   git fetch origin peter
   git switch main
   git pull --ff-only origin main
   git switch -c fix/descriptive-name
   python scripts/agent_review_workflow.py start \
     --title "fix: descriptive name" \
     --summary "Short statement of intended behavior" \
     --agent Basil
   ```

2. Make changes and commit locally.

3. Run checks and record them.

   ```bash
   git diff --check
   python scripts/agent_review_workflow.py test \
     --command "git diff --check" \
     --result pass

   python -m pytest tests/path/to/test.py
   python scripts/agent_review_workflow.py test \
     --command "python -m pytest tests/path/to/test.py" \
     --result pass
   ```

4. Send the local diff to one or more review agents without pushing.

   ```bash
   git diff origin/main...HEAD > /tmp/hermes-review.patch
   # Give /tmp/hermes-review.patch to GPT Code Review, Codex, Claude, etc.
   ```

5. Record each review report.

   ```bash
   python scripts/agent_review_workflow.py review \
     --agent "GPT Code Review" \
     --verdict changes-requested \
     --file /tmp/gpt-review.md
   ```

6. Fix findings, rerun checks, and record the new status.

7. Generate the PR body from the local ledger.

   ```bash
   python scripts/agent_review_workflow.py pr-body > /tmp/pr-body.md
   ```

8. Push only when ready to publish.

   ```bash
   git push -u peter HEAD
   gh pr create \
     --repo NousResearch/hermes-agent \
     --head PeterBerthelsen:$(git branch --show-current) \
     --base main \
     --title "fix: descriptive name" \
     --body-file /tmp/pr-body.md
   ```

## Local Issue Tracking

Create local/private issue records when a task is not ready for GitHub:

```bash
python scripts/agent_review_workflow.py issue \
  --title "Investigate flaky Slack gateway test" \
  --body "Observed during local review; keep private until confirmed." \
  --agent Basil \
  --branch "$(git branch --show-current)"
```

If the issue becomes upstream-relevant, create a GitHub issue later and add its number to the branch record or PR body.

## Multi-Agent Rules

- Each agent writes reviews through `scripts/agent_review_workflow.py review` instead of scattering notes in chat logs.
- Agents should not overwrite another agent's review report. The script timestamps each report.
- Findings that block merge should become commits or explicit PR checklist items before push.
- The public PR body may mention that local agent reviews were performed, but do not paste private prompts, raw model traces, secrets, or unrelated notes.
- Use local worktrees for parallel implementation branches: `.worktrees/` is already ignored.

## Quick Status

```bash
python scripts/agent_review_workflow.py status
```

This prints the current branch record, working-tree changes, and diff stat as JSON so any agent can pick up the state without searching Slack history.
