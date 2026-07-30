#!/usr/bin/env python3
"""pin_deliver -- re-inject pristine pin state into a session's context after a compaction.

NOT registered in .claude/settings.json (see DESIGN.md section 3.4). Invoke manually to test:

    echo '{"hook_event_name":"SessionStart","session_id":"<sid>"}' | \
        python "My Projects/Alzheimer/hooks/pin_deliver.py"
    echo '{"hook_event_name":"PostToolUse","session_id":"<sid>"}' | \
        python "My Projects/Alzheimer/hooks/pin_deliver.py"

Separate file from .claude/hooks/session_bus_drain.py on purpose -- that hook is owned by another
live session (see BRIEF.md) and delivers peer/self bus correspondence, an unrelated concern. Both
can be registered on the same events side by side; Claude Code hook config is a list per event.

Registered (once wired in) on SessionStart + PostToolUse, mirroring session_bus_drain.py's proven
event choice: SessionStart covers a session resuming after being down/compacted; PostToolUse
covers mid-session delivery within seconds of the next tool call.

Delivery is gated by pins.deliver_if_new_generation() -- see its docstring and DESIGN.md section
4.6. This is what keeps the PostToolUse hot path cheap and non-spammy: a session with no pins, or
one that has already been delivered for the current compaction generation, costs one small JSON
read and exits.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    from pins import deliver_if_new_generation
except Exception:
    sys.exit(0)  # fail-open


def main() -> int:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        return 0

    event = payload.get("hook_event_name") or ""
    if event not in ("SessionStart", "PostToolUse"):
        return 0

    sid = payload.get("session_id") or os.environ.get("CLAUDE_CODE_SESSION_ID") or ""
    if not sid:
        return 0

    try:
        text, _info = deliver_if_new_generation(sid)
    except Exception:
        return 0  # a pins bug must never block a real tool call or session start

    if not text:
        return 0

    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": event,
        "additionalContext": text,
    }}))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
