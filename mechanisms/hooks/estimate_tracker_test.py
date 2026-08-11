import json
import os
import runpy
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
m = runpy.run_path(os.path.join(HERE, "estimate_tracker.py"))

parse_estimate = m["parse_estimate"]
NOTIFICATION = m["NOTIFICATION"]

fails = 0


def check(label, got, want):
    global fails
    ok = got == want
    fails += 0 if ok else 1
    print(f"{'ok  ' if ok else 'FAIL'} {label}: got={got!r} want={want!r}")


# -- parse_estimate: the PreToolUse gate's core logic --
check("plain minutes", parse_estimate("do the thing\nESTIMATE: 20m\nmore text")[0], 1200.0)
check("hours, decimal", parse_estimate("ESTIMATE: 1.5h")[0], 5400.0)
check("seconds", parse_estimate("ESTIMATE: 90s")[0], 90.0)
check("days", parse_estimate("ESTIMATE: 2d")[0], 172800.0)
check("verbose unit", parse_estimate("ESTIMATE: 3 minutes")[0], 180.0)
check("case insensitive label", parse_estimate("estimate: 5m")[0], 300.0)
check("missing entirely -> (None, None)", parse_estimate("no estimate line here"), (None, None))
check("skip escape -> seconds is None", parse_estimate("ESTIMATE: skip exploratory only")[0], None)
check("skip escape -> raw carries reason",
      parse_estimate("ESTIMATE: skip exploratory only")[1], "skip exploratory only")
check("garbage after label -> (None, raw)", parse_estimate("ESTIMATE: dunno")[0], None)

# -- NOTIFICATION: the Stop-hook's transcript scan --
sample = (
    "<task-notification>\n<task-id>a4fde73e13fd70749</task-id>\n<status>completed</status>\n"
    "<result>...<usage><subagent_tokens>1000</subagent_tokens>"
    "<duration_ms>401885</duration_ms></usage></result>\n</task-notification>"
)
found = dict((a, int(d)) for a, d in NOTIFICATION.findall(sample))
check("extracts agentId+duration from a notification block",
      found.get("a4fde73e13fd70749"), 401885)

no_match = "just some prose about a4fde73e13fd70749 with no notification structure at all"
check("does not fire on a bare agentId mention with no duration",
      dict(NOTIFICATION.findall(no_match)), {})

# -- End-to-end: PreToolUse -> PostToolUse (background) -> Stop-hook reconciliation --
# Redirect the module's file paths into a scratch dir so this never touches real state.
with tempfile.TemporaryDirectory() as tmp:
    os.environ["ESTIMATE_TRACKER_STATE_DIR"] = tmp

    session = "test-session"
    pre_payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Agent",
        "session_id": session,
        "tool_input": {
            "description": "port the widget",
            "prompt": "Do the thing.\nESTIMATE: 10m\n",
            "subagent_type": "general-purpose",
        },
    }
    import io, contextlib
    captured = io.StringIO()
    try:
        with contextlib.redirect_stdout(captured):
            m["handle_pre"](pre_payload)
        pre_denied = False
    except SystemExit as e:
        pre_denied = e.code not in (0, None)
    check("valid ESTIMATE does not deny the dispatch", pre_denied, False)

    # The subagent must never see the ESTIMATE line -- it is tracking metadata, not an
    # instruction, and an agent that reads it as a budget will self-terminate against it well
    # short of the work being done (measured 2026-08-08: 13/89 cards, ~32 of ~120 min used,
    # reported "ran out of time"). `updatedInput.prompt` is what the subagent actually receives.
    out = json.loads(captured.getvalue())
    redacted_prompt = out["hookSpecificOutput"]["updatedInput"]["prompt"]
    check("ESTIMATE line is stripped from what the subagent receives",
          "ESTIMATE" in redacted_prompt, False)
    check("the rest of the prompt survives redaction intact",
          redacted_prompt, "Do the thing.\n")

    # The `description` field is the intended carrier: the estimate never enters the prompt, so
    # there is nothing to redact and nothing a human reading the transcript has to skip past.
    # Negative control below: an estimate in NEITHER field must still deny, otherwise this pair
    # of checks would pass against a hook that simply stopped enforcing anything.
    desc_payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Agent",
        "session_id": "desc-session",
        "tool_input": {
            "description": "port the widget ESTIMATE: 15m",
            "prompt": "Do the thing.\n",
            "subagent_type": "general-purpose",
        },
    }
    captured_desc = io.StringIO()
    try:
        with contextlib.redirect_stdout(captured_desc):
            m["handle_pre"](desc_payload)
        desc_denied = False
    except SystemExit as e:
        desc_denied = e.code not in (0, None)
    check("ESTIMATE in description alone does not deny", desc_denied, False)
    check("description carrier leaves the prompt untouched (no updatedInput)",
          captured_desc.getvalue().strip(), "")
    desc_state = json.load(open(os.path.join(tmp, "estimate-registry-desc-session.json")))
    check("description carrier still records the estimate",
          desc_state["pending"][0]["estimate_seconds"], 900.0)

    none_payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Agent",
        "session_id": "none-session",
        "tool_input": {
            "description": "port the widget",
            "prompt": "Do the thing.\n",
            "subagent_type": "general-purpose",
        },
    }
    none_out = io.StringIO()
    try:
        with contextlib.redirect_stdout(none_out):
            m["handle_pre"](none_payload)
    except SystemExit:
        pass
    check("NEGATIVE CONTROL: no estimate in either field still denies",
          json.loads(none_out.getvalue())["hookSpecificOutput"]["permissionDecision"], "deny")

    post_payload = {
        "hook_event_name": "PostToolUse",
        "tool_name": "Agent",
        "session_id": session,
        "tool_input": {"description": "port the widget", "subagent_type": "general-purpose"},
        "tool_response": {"agentId": "a4fde73e13fd70749deadbeef"},
    }
    try:
        m["handle_post"](post_payload)
    except SystemExit:
        pass

    state_path = m["_state_path"](session)
    state = m["_load"](state_path)
    check("post-hook links the dispatch and parks it (no duration yet)",
          [e["agentId"] for e in state.get("linked", [])],
          ["a4fde73e13fd70749deadbeef"])

    # A real transcript JSONL, shaped like the harness actually writes one -- exercises the
    # parsing in _read_transcript_text too, rather than mocking it away.
    transcript_path = os.path.join(tmp, "transcript.jsonl")
    notif_text = sample.replace("a4fde73e13fd70749", "a4fde73e13fd70749deadbeef")
    with open(transcript_path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"message": {"content": "irrelevant earlier turn"}}) + "\n")
        fh.write(json.dumps({"message": {"content": [{"type": "text", "text": notif_text}]}}) + "\n")

    stop_payload = {
        "hook_event_name": "Stop",
        "session_id": session,
        "transcript_path": transcript_path,
    }
    m["check_stop"](stop_payload)

    results_path = m["_results_path"]()
    results = []
    if os.path.isfile(results_path):
        with open(results_path, encoding="utf-8") as fh:
            results = [json.loads(line) for line in fh]
    check("stop-hook reconciliation appends exactly one result", len(results), 1)
    if results:
        r = results[0]
        check("recorded estimate matches what was dispatched", r["estimate_seconds"], 600.0)
        check("recorded actual matches the notification's duration_ms", r["actual_seconds"], 401.885)
        check("delta is actual minus estimate",
              round(r["delta_seconds"], 3), round(401.885 - 600.0, 3))

    state = m["_load"](state_path)
    check("reconciled entry is removed from the linked-pending list", state.get("linked", []), [])

print()
print(f"{'ALL PASS' if fails == 0 else f'{fails} FAILED'}")
