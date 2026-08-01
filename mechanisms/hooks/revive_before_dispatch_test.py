#!/usr/bin/env python3
"""Tests for revive_before_dispatch.py.

The load-bearing one is `test_positive_control_guard_can_actually_block`: a guard that never
fires passes every "it did not block me" assertion, so the suite must prove it CAN block before
any assertion that it did not is worth anything. That mistake has been made in this repo before
(a throwaway test that asserted a payload was absent, without first asserting the probe rendered).

Run: python -m pytest mechanisms/hooks/revive_before_dispatch_test.py -q
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).with_name("revive_before_dispatch.py")

_spec = importlib.util.spec_from_file_location("revive_before_dispatch", HOOK)
mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(mod)


def run_hook(payload: dict, state_dir: Path) -> tuple[int, str]:
    """Run the hook as a real subprocess, with STATE_DIR pointed at a tmp path."""
    driver = (
        "import json,sys,runpy,os\n"
        f"import importlib.util\n"
        f"spec=importlib.util.spec_from_file_location('h', r'{HOOK}')\n"
        "m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)\n"
        f"m.STATE_DIR=r'{state_dir}'\n"
        f"m.LOG=os.path.join(r'{state_dir}','revive-guard.log')\n"
        "m.main()\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", driver],
        input=json.dumps(payload), capture_output=True, text=True, timeout=30,
    )
    return proc.returncode, proc.stdout


def post(session: str, subagent: str, agent_id: str, desc: str = "a task") -> dict:
    return {
        "hook_event_name": "PostToolUse",
        "tool_name": "Agent",
        "session_id": session,
        "tool_input": {"subagent_type": subagent, "description": desc},
        "tool_response": {"agentId": agent_id},
    }


def pre(session: str, subagent: str, prompt: str = "do a thing") -> dict:
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": "Agent",
        "session_id": session,
        "tool_input": {"subagent_type": subagent, "prompt": prompt},
    }


def is_deny(stdout: str) -> bool:
    if not stdout.strip():
        return False
    try:
        out = json.loads(stdout)
    except ValueError:
        return False
    return out.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"


# --------------------------------------------------------------------------- positive control

def test_positive_control_guard_can_actually_block(tmp_path):
    """MUST come first in spirit: prove the guard fires at all, or no negative test means anything."""
    run_hook(post("s1", "iotta-server", "a1234567890abcd"), tmp_path)
    code, out = run_hook(pre("s1", "iotta-server"), tmp_path)
    assert is_deny(out), f"guard did not block a same-type re-dispatch; stdout={out!r}"
    assert code == 0, "a hook must exit 0 even when denying"


# --------------------------------------------------------------------------- must NOT block

def test_first_dispatch_of_a_type_is_allowed(tmp_path):
    _, out = run_hook(pre("s1", "iotta-server"), tmp_path)
    assert not is_deny(out)


def test_different_subagent_type_is_allowed(tmp_path):
    run_hook(post("s1", "iotta-server", "a1234567890abcd"), tmp_path)
    _, out = run_hook(pre("s1", "iotta-firmware"), tmp_path)
    assert not is_deny(out)


def test_other_session_does_not_block(tmp_path):
    """Cross-session revival is impossible, so a prior session must never produce a block."""
    run_hook(post("s1", "iotta-server", "a1234567890abcd"), tmp_path)
    _, out = run_hook(pre("s2", "iotta-server"), tmp_path)
    assert not is_deny(out)


def test_escape_hatch_allows_and_is_logged(tmp_path):
    run_hook(post("s1", "iotta-scout", "a1234567890abcd"), tmp_path)
    _, out = run_hook(
        pre("s1", "iotta-scout", "cold-required: adversarial verify must not be contaminated"),
        tmp_path,
    )
    assert not is_deny(out)
    log = (tmp_path / "revive-guard.log").read_text(encoding="utf-8")
    assert "ESCAPE" in log and "adversarial" in log


def test_non_agent_tool_is_ignored(tmp_path):
    payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "session_id": "s1",
               "tool_input": {"command": "ls"}}
    _, out = run_hook(payload, tmp_path)
    assert not is_deny(out)


def test_fails_open_on_garbage_payload(tmp_path):
    proc = subprocess.run(
        [sys.executable, str(HOOK)], input="not json at all",
        capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode == 0
    assert not is_deny(proc.stdout)


# --------------------------------------------------------------------------- the deny's content

def test_block_names_the_exact_replacement():
    """A block that only says 'don't' makes the agent guess — this project's own rule."""
    prior = [{"agentId": "a1234567890abcd", "description": "decode coredumps", "at": "2026-08-01T12:00:00"}]
    reason = mod.block_reason("iotta-firmware", prior)
    assert "SendMessage" in reason
    assert "a1234567890abcd" in reason
    assert "cold-required:" in reason, "the escape hatch must be discoverable from the block itself"
    assert "194,017" in reason, "the block must state that revival is not free"


def test_block_lists_earlier_agents_too():
    prior = [
        {"agentId": "a1111111111111a", "description": "first", "at": "2026-08-01T12:00:00"},
        {"agentId": "a2222222222222b", "description": "second", "at": "2026-08-01T12:30:00"},
    ]
    reason = mod.block_reason("iotta-server", prior)
    assert "a2222222222222b" in reason, "the newest must be the one offered"
    assert "a1111111111111a" in reason, "earlier agents must still be visible"


# --------------------------------------------------------------------------- agentId extraction

def test_agent_id_extracted_from_prose_result():
    """The result shape is not guaranteed; the id may only be present in free text."""
    got = mod.agent_id_from("Async agent launched.\nagentId: a5a59c06e471d8d06 (internal)")
    assert got == "a5a59c06e471d8d06"


def test_agent_id_absent_is_none_not_a_crash():
    assert mod.agent_id_from({"status": "ok"}) is None


def test_duplicate_post_does_not_double_record(tmp_path):
    run_hook(post("s1", "iotta-sdk", "a1234567890abcd"), tmp_path)
    run_hook(post("s1", "iotta-sdk", "a1234567890abcd"), tmp_path)
    state = json.loads((tmp_path / "agent-registry-s1.json").read_text(encoding="utf-8"))
    assert len(state["iotta-sdk"]) == 1
