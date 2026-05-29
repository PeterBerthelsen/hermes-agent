# Incident Note: Codex Responses `NoneType` Failure Loop

Date: 2026-05-26
Author: Codex investigation handoff

## Summary

Hermes Gateway began returning repeated model fallback failures for OpenAI Codex Responses calls. The visible user symptom was a Slack response loop ending in:

```text
'NoneType' object is not iterable
Non-retryable client error
```

The fallback chain repeatedly attempted:

```text
gpt-5.5 -> gpt-5.3-codex -> gpt-5.4-mini
```

The failure affected both the active Slack session and fresh cron jobs, so it was not only a corrupted conversation history issue.

Update after deeper tracing: the root cause was not the request body. The OpenAI Python SDK Responses stream parser crashed when the Codex backend emitted a terminal completed response snapshot with `response.output = None`. Hermes had already received useful `response.output_item.done` events before that terminal frame, but the SDK crashed before Hermes could call `get_final_response()`.

## User Request That Failed

The active Slack session was `20260526_192350_20bf95d8`. The substantial user request was to continue a broad Obsidian MCP / vault overhaul:

```text
Okay. Let's keep Obsidian... Can you put all of that in place and making Obsidian MCP a powerhouse...
Add the machine layers... Joseph coming in... revamping the whole vault...
setup multi-step cleanup, then make a cron... Go go go!
```

Hermes started the job, created initial todos, and began auditing terminal / cron / Obsidian context, but failed before durable vault, script, or cron work was completed.

## Observed Timeline

- Around 19:33 EDT: Slack session `20260526_192350_20bf95d8` failed with `TypeError: 'NoneType' object is not iterable`.
- Around 20:01 EDT: fresh cron sessions with no chat history failed with the same error.
- Around 20:13 EDT: the user asked Slack to resume the overhaul, and the same fallback loop occurred.
- Around 20:33 EDT: the user tried "please continue", and the same loop occurred again.
- Around 20:42 EDT: the latest committed runtime change was reverted.
- Around 20:43 EDT: `hermes-gateway.service` was restarted after the revert.
- Around 21:06 EDT: traceback capture showed the crash frame inside the OpenAI SDK parser.
- Around 21:09 EDT: Hermes was patched to recover from the SDK stream parser crash and a real one-shot diagnostic returned `OK`.

## Relevant Logs And Dumps

Important request dumps:

```text
/home/peter/.hermes/sessions/request_dump_20260526_192350_20bf95d8_20260526_203352_651229.json
/home/peter/.hermes/sessions/request_dump_cron_64707631de84_20260526_203008_20260526_203018_937412.json
/home/peter/.hermes/sessions/request_dump_20260526_192350_20bf95d8_20260526_201348_333921.json
/home/peter/.hermes/sessions/request_dump_cron_8c902fe7c0b0_20260526_200057_20260526_200116_784768.json
```

Important log file:

```text
/home/peter/.hermes/logs/errors.log
```

## First Hypothesis: Bad Codex Message Replay

The first suspected issue was replaying assistant `codex_message_items` with `phase: "commentary"` or `phase: "analysis"` into a later Responses request. That is suspicious because those are internal assistant phases, not normal prior assistant output.

Patch made:

- File: `agent/codex_responses_adapter.py`
- Behavior: skip replaying stored assistant message items whose phase is `commentary` or `analysis`.
- Test added: `test_commentary_message_items_are_not_replayed`

Validation:

```text
venv/bin/python -m pytest tests/agent/transports/test_codex_transport.py -q
40 passed
```

Result:

This was not sufficient. Fresh cron jobs with history length 0 still failed, so bad message replay was not the root cause.

## Second Hypothesis: Null Metadata In Tool Schemas

Fresh request dumps contained JSON schema values with `default: null` inside two Acellus MCP tool schemas:

```text
mcp_acellus_acellus_collect_all_course_reports
mcp_acellus_acellus_render_daily_report
```

The specific property was:

```text
parameters.properties.max_courses.default = null
parameters.properties.max_courses.nullable = true
```

Patch made:

- File: `agent/codex_responses_adapter.py`
- Behavior: sanitize outgoing Codex Responses tool schemas by stripping Python `None` values and non-standard `nullable` hints.
- Test added: `test_convert_tools_strips_null_schema_metadata`

Validation:

```text
venv/bin/python -m pytest tests/agent/transports/test_codex_transport.py -q
41 passed
```

Captured failing request replayed through preflight with the patch:

```text
none_count 0
mcp_acellus_acellus_collect_all_course_reports max_courses {'type': 'integer'}
mcp_acellus_acellus_render_daily_report max_courses {'type': 'integer'}
```

Result:

This also was not sufficient. The user retried from Slack at 20:33 EDT and hit the same `NoneType` failure loop.

## Reverted Change

The latest committed change before the failures was:

```text
8c9a3f82b fix: backport kanban fd corruption guard
```

It touched the model / OpenAI client runtime path:

```text
agent/agent_runtime_helpers.py
agent/chat_completion_helpers.py
run_agent.py
tests/run_agent/test_create_openai_client_reuse.py
tests/run_agent/test_tls_fd_recycle_corruption.py
```

Because the failure persisted after payload sanitation, this commit became the most plausible recent regression. It was reverted with:

```text
56ef89a17 Revert "fix: backport kanban fd corruption guard"
```

After the revert, `hermes-gateway.service` was restarted.

This revert did not resolve the issue. It remains in history as:

```text
56ef89a17 Revert "fix: backport kanban fd corruption guard"
```

Do not assume the reverted commit was the root cause. The later traceback showed the immediate failure was the SDK parser receiving `response.output = None`.

## Confirmed Root Cause

Traceback captured after adding `exc_info=True` and embedding traceback text in request dumps:

```text
File ".../agent/codex_runtime.py", line 196, in run_codex_stream
  for event in stream:
File ".../site-packages/openai/lib/streaming/responses/_responses.py", line 57, in __stream__
  events_to_fire = self._state.handle_event(sse_event)
File ".../site-packages/openai/lib/streaming/responses/_responses.py", line 360, in accumulate_event
  self._completed_response = parse_response(...)
File ".../site-packages/openai/lib/_parsing/_responses.py", line 61, in parse_response
  for output in response.output:
TypeError: 'NoneType' object is not iterable
```

The request body in the fresh Slack dump had no Python/JSON null values:

```text
none_count_body 0
```

So the backend/SDK stream shape, not the outgoing request schema, was the direct failure.

## Final Patch

File:

```text
agent/codex_runtime.py
```

Behavior:

- During `responses.stream(...)`, Hermes already collects `response.output_item.done` events and streamed text deltas.
- If the OpenAI SDK raises `TypeError("'NoneType' object is not iterable")` while processing the terminal completed event, Hermes now synthesizes a minimal completed response from the collected output items or streamed text.
- This prevents the false fallback chain when Codex produced usable output but the SDK terminal snapshot had `output=None`.

Additional diagnostics retained:

```text
agent/agent_runtime_helpers.py
agent/conversation_loop.py
```

These now preserve traceback information for non-retryable client errors and request dumps, making future failures easier to diagnose.

Regression test:

```text
tests/run_agent/test_run_agent_codex_responses.py::test_run_codex_stream_recovers_when_completed_snapshot_has_null_output
```

Validation:

```text
venv/bin/python -m pytest \
  tests/run_agent/test_run_agent_codex_responses.py::test_run_codex_stream_recovers_when_completed_snapshot_has_null_output \
  tests/run_agent/test_run_agent_codex_responses.py::test_run_codex_stream_fallback_parses_create_stream_events \
  tests/agent/transports/test_codex_transport.py -q

43 passed
```

Real one-shot verification:

```text
venv/bin/python -m hermes_cli.main -z "diagnostic ping: reply with only OK"
```

Result:

```text
OK
```

Log confirmation:

```text
Codex Responses stream parser received terminal response with output=None;
recovered from 1 collected item(s), streamed_chars=0.
```

## Current State

As of the final restart after the stream recovery patch:

- `hermes-gateway.service` was active.
- Slack, Telegram, and Discord were connected.
- A real minimal Hermes Codex one-shot returned `OK`.
- Existing old `NoneType` entries remain in `errors.log`; use timestamps after 21:09 EDT when checking for recurrence.

The user's substantial Obsidian overhaul request should be considered incomplete. Do not assume vault, script, or cron changes were successfully applied from that failed turn.

## Guidance Before Trying Again

Before attempting the Obsidian overhaul again:

1. Confirm the gateway is running on the reverted commit or later:

```text
git log --oneline -3
```

Expected to include:

```text
56ef89a17 Revert "fix: backport kanban fd corruption guard"
```

2. Check for new post-restart errors:

```text
tail -n 80 /home/peter/.hermes/logs/errors.log
```

3. If the same error repeats, do not keep retrying the same Slack session. Inspect the newest `request_dump_*` file first.

4. Compare the newest dump against the prior dumps. Specifically check:

- Whether `request.body.tools` still contains any `null` values.
- Whether the failure happens before or after the HTTP request leaves the OpenAI client.
- Whether the stack points into `agent/chat_completion_helpers.py`, `agent/agent_runtime_helpers.py`, or the OpenAI SDK.

5. If `8c9a3f82b` needs to be reintroduced later, test it independently. It was not the confirmed root cause of this incident.

## Files Intentionally Changed During Investigation

These local files were changed by this investigation and remain in the dirty tree unless later committed or reverted:

```text
agent/agent_runtime_helpers.py
agent/codex_responses_adapter.py
agent/codex_runtime.py
agent/conversation_loop.py
tests/agent/transports/test_codex_transport.py
tests/run_agent/test_run_agent_codex_responses.py
docs/incident-codex-responses-nonetype-2026-05-26.md
```

There were many other dirty files in the working tree before this investigation. Do not bulk reset the repository unless Peter explicitly asks for it.
