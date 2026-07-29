#!/usr/bin/env python3
"""Tests for context_ledger.py.

The benign cases are the point: a detector that fires on one big legitimate Read, or nags every
turn once a leak exists, gets disabled and takes its true positives with it.
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.path.join(HERE, "context_ledger.py")
sys.path.insert(0, HERE)
import context_ledger as cl  # noqa: E402

SESSION = "unittest-ctx-ledger"


def _err_entry(text):
    return {"type": "user", "message": {"content": [{"type": "tool_result", "content": text}]}}


def _write(entries):
    fd, path = tempfile.mkstemp(suffix=".jsonl")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        for e in entries:
            fh.write(json.dumps(e) + "\n")
    return path


def _run(transcript, session=SESSION, stop_active=False):
    payload = json.dumps({"transcript_path": transcript, "session_id": session,
                          "stop_hook_active": stop_active})
    r = subprocess.run([sys.executable, HOOK], input=payload, capture_output=True, text=True)
    return r.stdout.strip()


def _blocks(out):
    try:
        return json.loads(out).get("decision") == "block" if out else False
    except Exception:
        return False


def _clear_state():
    p = cl._state_path(SESSION)
    if os.path.exists(p):
        os.unlink(p)


def _check(name, cond):
    print(f"{'ok  ' if cond else 'FAIL'} {name}")
    return cond


def main() -> int:
    results = []
    _clear_state()

    # A real leak: 60 identical ~1.2 KB error strings = ~72 KB, count 60. BLOCKS, once.
    leak = ("Python was not found; run without arguments to install from the Microsoft Store, "
            "or disable this shortcut from Settings. " * 12)
    p = _write([{"type": "assistant", "message": {"content": [{"type": "text", "text": "hi"}]}}]
               + [_err_entry(leak) for _ in range(60)])
    out1 = _run(p)
    results.append(_check("real leak BLOCKS", _blocks(out1)))
    results.append(_check("names it as a hook/plugin error", "hook" in out1.lower()))
    results.append(_check("reports the count", "60x" in out1 or "60" in out1))

    # Fires ONCE: same session, same transcript -> quiet the second time.
    out2 = _run(p)
    results.append(_check("does NOT nag again (fire-once)", not _blocks(out2)))
    os.unlink(p)
    _clear_state()

    # Benign: one big legitimate Read (200 KB, count 1) -> quiet.
    big = "x" * 200_000
    p = _write([_err_entry(big)])
    results.append(_check("one big Read -> quiet (count<50)", not _blocks(_run(p))))
    os.unlink(p)
    _clear_state()

    # Benign: 60 SMALL identical strings (~100 B each = 6 KB total) -> quiet (byte floor).
    p = _write([_err_entry("short repeated line") for _ in range(60)])
    results.append(_check("many tiny repeats -> quiet (bytes<floor)", not _blocks(_run(p))))
    os.unlink(p)
    _clear_state()

    # stop_hook_active -> quiet (no loop).
    p = _write([_err_entry(leak) for _ in range(60)])
    results.append(_check("stop_hook_active -> quiet", not _blocks(_run(p, stop_active=True))))
    os.unlink(p)
    _clear_state()

    passed = sum(1 for r in results if r)
    print(f"\n{passed}/{len(results)} passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
