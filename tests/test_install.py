"""Tests for install.py -- run against a throwaway settings file, never
the real .claude/settings.local.json.

Run: python -m pytest "tests/test_install.py" -q
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import install as I  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(I, "SETTINGS_PATH", tmp_path / "settings.local.json")
    yield


def test_install_from_scratch_adds_all_three_events():
    changed = I.install()
    assert all(changed.values())
    st = I.status()
    assert all(st.values())


def test_install_is_idempotent():
    I.install()
    changed_again = I.install()
    assert not any(changed_again.values())


def test_dry_run_writes_nothing():
    changed = I.install(dry_run=True)
    assert all(changed.values())
    assert not I.SETTINGS_PATH.exists()


def test_uninstall_removes_only_our_entries_preserves_others():
    """Must not clobber the existing session_bus_drain.py / session_continuity.py registrations
    this installer is documented to sit alongside, never replace."""
    existing = {
        "hooks": {
            "PostToolUse": [
                {"matcher": "", "hooks": [
                    {"type": "command", "command": '"python" ".claude/hooks/session_bus_drain.py"'},
                ]},
            ],
            "PreCompact": [
                {"matcher": "", "hooks": [
                    {"type": "command", "command": '"python" ".claude/hooks/session_continuity.py"',
                     "timeout": 15},
                ]},
            ],
        }
    }
    I.SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    I.SETTINGS_PATH.write_text(json.dumps(existing, indent=2), encoding="utf-8")

    I.install()
    data = json.loads(I.SETTINGS_PATH.read_text(encoding="utf-8"))
    assert _has_command(data, "PostToolUse", "session_bus_drain.py")
    assert _has_command(data, "PreCompact", "session_continuity.py")
    assert _has_command(data, "PostToolUse", "pin_deliver.py")
    assert _has_command(data, "PreCompact", "pin_precompact.py")

    I.uninstall()
    data = json.loads(I.SETTINGS_PATH.read_text(encoding="utf-8"))
    assert _has_command(data, "PostToolUse", "session_bus_drain.py")   # untouched
    assert _has_command(data, "PreCompact", "session_continuity.py")  # untouched
    assert not _has_command(data, "PostToolUse", "pin_deliver.py")    # removed
    assert not _has_command(data, "PreCompact", "pin_precompact.py")  # removed


def test_precompact_entry_carries_timeout():
    I.install()
    data = json.loads(I.SETTINGS_PATH.read_text(encoding="utf-8"))
    entry = data["hooks"]["PreCompact"][-1]["hooks"][0]
    assert entry.get("timeout") == 15


def test_status_reflects_partial_install():
    data = {"hooks": {"PreCompact": [{"matcher": "", "hooks": [
        {"type": "command", "command": I._command_for(I.HOOK_SPECS[0][1])},
    ]}]}}
    I.SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    I.SETTINGS_PATH.write_text(json.dumps(data), encoding="utf-8")
    st = I.status()
    assert st["PreCompact"] is True
    assert st["SessionStart"] is False
    assert st["PostToolUse"] is False


def test_malformed_json_refused_not_overwritten():
    I.SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    I.SETTINGS_PATH.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(SystemExit):
        I.install()
    assert I.SETTINGS_PATH.read_text(encoding="utf-8") == "{not valid json"  # untouched


def _has_command(data: dict, event: str, needle: str) -> bool:
    for group in data.get("hooks", {}).get(event, []):
        for h in group.get("hooks", []):
            if needle in (h.get("command") or ""):
                return True
    return False
