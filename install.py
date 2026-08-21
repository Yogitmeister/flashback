#!/usr/bin/env python3
"""Flashback pins -- installer.

Registers (or removes) hooks/pin_precompact.py and hooks/pin_deliver.py in this repo's
.claude/settings.local.json -- the gitignored, per-machine hook config every session in THIS repo
already reads (see .gitignore, and the existing session_bus_drain.py / session_continuity.py
entries this installer sits alongside, never replaces). Never touches the git-tracked
.claude/settings.json: that file is shared across every clone of this repo, and a hook
registration is a machine-local decision, not a checked-in one -- same reasoning DESIGN.md section
3.4 gave for not doing this silently at build time.

Idempotent: safe to run repeatedly. Detects an existing entry by checking whether any already-
registered command string references this file's own absolute path, so re-running after moving
the repo (a different absolute path) correctly adds a fresh entry rather than leaving a dangling
old one -- run --uninstall first if you've moved the repo.

Every path is derived from this file's own location (Path(__file__).resolve()) and
sys.executable, never hardcoded to one machine or user -- and REPO_ROOT reuses pins.py's own
_detect_repo_root() (walk up to the nearest .git, fall back to this file's own directory) rather
than a hardcoded nesting depth, so it stays correct however deep this tool ends up vendored inside
the project it protects. What this does NOT yet solve: a single install pointed at more than one
target project (see the project README's Status section) -- one clone of this tool still only
targets whichever repo it's vendored inside.

Usage:
    python install.py             install (idempotent)
    python install.py --dry-run   show what would change, write nothing
    python install.py --verify    exit 0 if fully installed, 1 otherwise, prints status
    python install.py --uninstall remove Flashback's entries, leave everything else untouched
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pins import _detect_repo_root  # noqa: E402

FLASHBACK_DIR = Path(__file__).resolve().parent
REPO_ROOT = _detect_repo_root()
SETTINGS_PATH = REPO_ROOT / ".claude" / "settings.local.json"

HOOK_SPECS = [
    ("PreCompact", FLASHBACK_DIR / "hooks" / "pin_precompact.py", 15),
    ("SessionStart", FLASHBACK_DIR / "hooks" / "pin_deliver.py", None),
    ("PostToolUse", FLASHBACK_DIR / "hooks" / "pin_deliver.py", None),
]


def _command_for(script: Path) -> str:
    py = sys.executable or "python"
    return f'"{py}" "{script}"'


def _load_settings() -> dict:
    if not SETTINGS_PATH.exists():
        return {}
    try:
        return json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise SystemExit(
            f"{SETTINGS_PATH} exists but is not valid JSON ({e}) -- fix or remove it by hand "
            f"before installing; this script will not overwrite a file it cannot safely parse."
        )


def _save_settings(data: dict) -> None:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = SETTINGS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, SETTINGS_PATH)


def _has_entry(groups: list, script: Path) -> bool:
    needle = str(script)
    for group in groups:
        for h in group.get("hooks", []):
            if needle in (h.get("command") or ""):
                return True
    return False


def status() -> dict:
    data = _load_settings()
    hooks = data.get("hooks", {})
    return {
        event: _has_entry(hooks.get(event, []), script)
        for event, script, _timeout in HOOK_SPECS
    }


def install(dry_run: bool = False) -> dict:
    for _event, script, _timeout in HOOK_SPECS:
        if not script.exists():
            raise SystemExit(f"expected hook script missing: {script}")

    data = _load_settings()
    hooks = data.setdefault("hooks", {})
    changed = {}

    for event, script, timeout in HOOK_SPECS:
        groups = hooks.setdefault(event, [])
        if _has_entry(groups, script):
            changed[event] = False
            continue
        entry = {"type": "command", "command": _command_for(script)}
        if timeout:
            entry["timeout"] = timeout
        groups.append({"matcher": "", "hooks": [entry]})
        changed[event] = True

    if any(changed.values()) and not dry_run:
        _save_settings(data)
    return changed


def _hook_count(groups: list) -> int:
    return sum(len(g.get("hooks", [])) for g in groups)


def uninstall(dry_run: bool = False) -> dict:
    data = _load_settings()
    hooks = data.get("hooks", {})
    changed = {}

    for event, script, _timeout in HOOK_SPECS:
        groups = hooks.get(event, [])
        needle = str(script)
        before = _hook_count(groups)

        kept = []
        for group in groups:
            surviving = [h for h in group.get("hooks", []) if needle not in (h.get("command") or "")]
            if surviving:
                kept.append({**group, "hooks": surviving})
        hooks[event] = kept

        changed[event] = _hook_count(kept) != before

    if any(changed.values()) and not dry_run:
        _save_settings(data)
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--uninstall", action="store_true")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()

    if args.verify:
        st = status()
        for event, installed in st.items():
            print(f"  {event:15s} {'installed' if installed else 'NOT installed'}")
        return 0 if all(st.values()) else 1

    if args.uninstall:
        changed = uninstall(dry_run=args.dry_run)
        for event, did in changed.items():
            print(f"  {event:15s} {'removed' if did else '(nothing to remove)'}")
        print(f"target: {SETTINGS_PATH}" + (" (dry run, nothing written)" if args.dry_run else ""))
        return 0

    changed = install(dry_run=args.dry_run)
    for event, did in changed.items():
        print(f"  {event:15s} {'added' if did else '(already installed)'}")
    print(f"target: {SETTINGS_PATH}" + (" (dry run, nothing written)" if args.dry_run else ""))
    if any(changed.values()) and not args.dry_run:
        print("\nRestart or start a new Claude Code session in this repo for the hooks to take effect.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
