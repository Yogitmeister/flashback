#!/usr/bin/env python3
"""pin_precompact -- advance the pin TTL clock once per real compaction.

NOT registered in .claude/settings.json (see DESIGN.md section 3.4) -- wiring this in is a
deliberate remaining step, not something this pass does silently to a shared, live-in-every-
session config file. Invoke manually to test:

    echo '{"hook_event_name":"PreCompact","session_id":"<sid>","trigger":"manual"}' | \
        python "hooks/pin_precompact.py"

Separate file from .claude/hooks/session_continuity.py on purpose -- that hook is owned by
another live session (see BRIEF.md) and does something different (transcript-tail extraction +
compaction steering for uncheckable decision/intent state). This one only touches the pins TTL
clock. Both can be registered on PreCompact side by side; Claude Code hook config is a list per
event, not a single slot.

Only touches the uncheckable-pin TTL counter and eviction -- deliberately does NOT run checkable
verification. That logic lives in exactly one place, pin_deliver.py, so a check is never
evaluated twice with a chance of two different results inside one compaction cycle. See
DESIGN.md section 4.4/4.6.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    from pins import precompact_pass
except Exception:
    sys.exit(0)  # fail-open: never wedge a compaction


def main() -> int:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        return 0

    if (payload.get("hook_event_name") or "") != "PreCompact":
        return 0

    sid = payload.get("session_id") or os.environ.get("CLAUDE_CODE_SESSION_ID") or ""
    if not sid:
        return 0

    try:
        result = precompact_pass(sid)
    except Exception:
        return 0  # a pins bug must never block a compaction the human asked for

    if result.get("remaining"):
        print(
            f"COMPACTION GUIDANCE (pin_precompact): {result['remaining']} pin(s) will be "
            f"re-verified and re-delivered after this compaction completes -- do not spend "
            f"summary space restating them."
        )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
