"""Tests for the portable JIT retriever.

The load-bearing properties, in the order they matter:

  1. fail-open   -- a broken config must never break a prompt
  2. portable    -- no path, corpus, or trigger from any particular project
  3. quiet       -- below threshold means no output at all
  4. determinism -- the same query yields the same context on every machine
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import jit  # noqa: E402

JIT_PY = str(Path(__file__).resolve().parents[1] / "jit.py")


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def write_note(directory: Path, slug: str, name: str, description: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{slug}.md"
    path.write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\nbody text\n",
        encoding="utf-8",
    )
    return path


def make_project(tmp_path: Path, sources: list[dict], **top) -> Path:
    cfg_dir = tmp_path / ".flashback"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "jit.json").write_text(
        json.dumps({"sources": sources, **top}), encoding="utf-8"
    )
    return tmp_path


def run_hook(mode: str, payload: dict, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, JIT_PY, mode],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=str(cwd),
    )


# --------------------------------------------------------------------------
# 1. fail-open
# --------------------------------------------------------------------------

def test_no_config_anywhere_is_silent_and_succeeds(tmp_path):
    result = run_hook("--prompt", {"prompt": "anything at all here"}, tmp_path)
    assert result.returncode == 0
    assert result.stdout == ""


def test_malformed_config_does_not_break_the_prompt(tmp_path):
    cfg_dir = tmp_path / ".flashback"
    cfg_dir.mkdir()
    (cfg_dir / "jit.json").write_text("{ this is not json", encoding="utf-8")
    result = run_hook("--prompt", {"prompt": "deploy the staging cluster"}, tmp_path)
    assert result.returncode == 0
    assert result.stdout == ""


def test_source_pointing_at_nothing_is_silent(tmp_path):
    root = make_project(tmp_path, [
        {"name": "notes", "format": "frontmatter", "glob": "does/not/exist/*.md"},
    ])
    result = run_hook("--prompt", {"prompt": "deploy the staging cluster"}, root)
    assert result.returncode == 0
    assert result.stdout == ""


def test_unreadable_entry_is_skipped_not_fatal(tmp_path):
    notes = tmp_path / "notes"
    write_note(notes, "good", "Deploy runbook", "How to deploy the staging cluster")
    (notes / "bad.md").write_bytes(b"\xff\xfe not valid utf-8 \x00")
    root = make_project(tmp_path, [
        {"name": "notes", "format": "frontmatter", "glob": "notes/*.md"},
    ])
    result = run_hook("--prompt", {"prompt": "deploy the staging cluster"}, root)
    assert result.returncode == 0
    assert "Deploy runbook" in result.stdout


def test_unknown_format_is_ignored(tmp_path):
    root = make_project(tmp_path, [{"name": "x", "format": "sqlite", "glob": "*.db"}])
    assert jit.load_source(jit.load_config(str(root)), {"format": "sqlite"}) == []


# --------------------------------------------------------------------------
# 2. output contract
# --------------------------------------------------------------------------

def test_prompt_hit_emits_valid_hook_json(tmp_path):
    write_note(tmp_path / "notes", "deploy",
               "Deploy runbook", "How to deploy the staging cluster safely")
    root = make_project(tmp_path, [
        {"name": "notes", "format": "frontmatter", "glob": "notes/*.md",
         "label": "Relevant notes"},
    ])
    result = run_hook("--prompt", {"prompt": "how do I deploy staging"}, root)
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    hook = payload["hookSpecificOutput"]
    assert hook["hookEventName"] == "UserPromptSubmit"
    assert "Deploy runbook" in hook["additionalContext"]
    assert "Relevant notes" in hook["additionalContext"]


def test_tool_mode_reports_its_own_event_name(tmp_path):
    write_note(tmp_path / "notes", "migrations",
               "Migration rules", "Rules for editing database migration files")
    root = make_project(tmp_path, [
        {"name": "notes", "format": "frontmatter", "glob": "notes/*.md"},
    ])
    result = run_hook("--tool", {
        "tool_name": "Edit",
        "tool_input": {"file_path": "db/migration/0002_add_rules.sql"},
    }, root)
    assert result.returncode == 0
    hook = json.loads(result.stdout)["hookSpecificOutput"]
    assert hook["hookEventName"] == "PreToolUse"
    assert "Migration rules" in hook["additionalContext"]


def test_tool_path_separators_become_query_terms():
    text = jit.query_text_for_tool({
        "tool_name": "Edit",
        "tool_input": {"file_path": "db/migration/0002_add.sql"},
    })
    assert "migration" in jit.tokenize(text)


def test_diagnostics_never_reach_stdout(tmp_path):
    write_note(tmp_path / "notes", "deploy", "Deploy runbook", "deploy staging cluster")
    root = make_project(tmp_path, [
        {"name": "notes", "format": "frontmatter", "glob": "notes/*.md"},
    ])
    result = subprocess.run(
        [sys.executable, JIT_PY, "--check", "--text", "deploy staging"],
        capture_output=True, text=True, cwd=str(root),
    )
    assert result.returncode == 0
    assert result.stdout == ""
    assert "Deploy runbook" in result.stderr


# --------------------------------------------------------------------------
# 3. quiet below threshold
# --------------------------------------------------------------------------

def test_unrelated_prompt_injects_nothing(tmp_path):
    write_note(tmp_path / "notes", "deploy", "Deploy runbook", "deploy the staging cluster")
    root = make_project(tmp_path, [
        {"name": "notes", "format": "frontmatter", "glob": "notes/*.md"},
    ])
    result = run_hook("--prompt", {"prompt": "write a haiku about otters"}, root)
    assert result.returncode == 0
    assert result.stdout == ""


def test_single_shared_word_is_not_enough(tmp_path):
    write_note(tmp_path / "notes", "deploy", "Deploy runbook", "deploy the staging cluster")
    root = make_project(tmp_path, [
        {"name": "notes", "format": "frontmatter", "glob": "notes/*.md"},
    ])
    # "deploy" alone shares one token; min_match_tokens defaults to 2.
    result = run_hook("--prompt", {"prompt": "deploy something unrelated entirely"}, root)
    assert result.stdout == ""


def test_off_switch_silences_everything(tmp_path):
    write_note(tmp_path / "notes", "deploy", "Deploy runbook", "deploy the staging cluster")
    root = make_project(tmp_path, [
        {"name": "notes", "format": "frontmatter", "glob": "notes/*.md"},
    ])
    (root / ".flashback" / "jit.off").write_text("", encoding="utf-8")
    result = run_hook("--prompt", {"prompt": "how do I deploy staging"}, root)
    assert result.returncode == 0
    assert result.stdout == ""


def test_max_hits_is_respected(tmp_path):
    notes = tmp_path / "notes"
    for i in range(6):
        write_note(notes, f"deploy{i}", f"Deploy runbook {i}",
                   "how to deploy the staging cluster safely")
    root = make_project(tmp_path, [
        {"name": "notes", "format": "frontmatter", "glob": "notes/*.md", "max_hits": 2},
    ])
    result = run_hook("--prompt", {"prompt": "how do I deploy the staging cluster"}, root)
    context = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
    assert context.count("Deploy runbook") == 2


# --------------------------------------------------------------------------
# 4. determinism and portability
# --------------------------------------------------------------------------

def test_equal_scores_resolve_by_name_not_filesystem_order(tmp_path):
    notes = tmp_path / "notes"
    # Identical descriptions => identical scores => the tie-break must be stable.
    for slug, name in [("z", "Alpha runbook"), ("a", "Zulu runbook"), ("m", "Mike runbook")]:
        write_note(notes, slug, name, "deploy the staging cluster safely")
    root = make_project(tmp_path, [
        {"name": "notes", "format": "frontmatter", "glob": "notes/*.md", "max_hits": 3},
    ])
    cfg = jit.load_config(str(root))
    query = jit.tokenize("deploy the staging cluster")
    hits = jit.select(cfg, query)[0][1]
    assert [h[1]["name"] for h in hits] == ["Alpha runbook", "Mike runbook", "Zulu runbook"]


def test_no_project_specific_identifiers_are_compiled_in():
    """The whole point of the port: nothing about one workspace survives in code."""
    source = Path(JIT_PY).read_text(encoding="utf-8")
    for leaked in ("memory-mirror", "cv-cl-factory", "linkedin-scraper",
                   "LLM_Wiki", "skills.manifest", "D:\\", "/d/CLAUDE"):
        assert leaked not in source, f"{leaked!r} leaked into the portable module"


def test_config_is_discovered_from_a_subdirectory(tmp_path):
    write_note(tmp_path / "notes", "deploy", "Deploy runbook", "deploy the staging cluster")
    root = make_project(tmp_path, [
        {"name": "notes", "format": "frontmatter", "glob": "notes/*.md"},
    ])
    deep = root / "src" / "api" / "handlers"
    deep.mkdir(parents=True)
    result = run_hook("--prompt", {"prompt": "how do I deploy staging"}, deep)
    assert "Deploy runbook" in result.stdout


def test_env_var_overrides_config_discovery(tmp_path, monkeypatch):
    write_note(tmp_path / "notes", "deploy", "Deploy runbook", "deploy the staging cluster")
    root = make_project(tmp_path, [
        {"name": "notes", "format": "frontmatter", "glob": "notes/*.md"},
    ])
    monkeypatch.setenv("FLASHBACK_JIT_CONFIG", str(root / ".flashback" / "jit.json"))
    cfg = jit.load_config(str(tmp_path.parent))
    assert cfg is not None
    assert Path(cfg.root) == root


# --------------------------------------------------------------------------
# 5. source formats
# --------------------------------------------------------------------------

def test_manifest_source_with_nested_entries(tmp_path):
    (tmp_path / "manifest.json").write_text(json.dumps({
        "categories": {
            "ops": {"items": [
                {"name": "deploy-runbook",
                 "description": "deploy the staging cluster safely",
                 "file": "ops/deploy.md"},
            ]},
        },
    }), encoding="utf-8")
    root = make_project(tmp_path, [
        {"name": "manifest", "format": "manifest", "path": "manifest.json",
         "entries_path": "categories"},
    ])
    result = run_hook("--prompt", {"prompt": "how do I deploy the staging cluster"}, root)
    assert "deploy-runbook" in result.stdout


def test_manifest_source_with_a_flat_list(tmp_path):
    (tmp_path / "flat.json").write_text(json.dumps([
        {"name": "deploy-runbook", "description": "deploy the staging cluster safely",
         "file": "ops/deploy.md"},
    ]), encoding="utf-8")
    root = make_project(tmp_path, [
        {"name": "flat", "format": "manifest", "path": "flat.json"},
    ])
    result = run_hook("--prompt", {"prompt": "how do I deploy the staging cluster"}, root)
    assert "deploy-runbook" in result.stdout


def test_body_source_injects_the_body_verbatim(tmp_path):
    digests = tmp_path / "digests"
    digests.mkdir()
    (digests / "safety.md").write_text(
        "---\nname: Safety rules\ndescription: rules for destructive commands\n---\n"
        "NEVER run a destructive command without an explicit path list.\n",
        encoding="utf-8",
    )
    root = make_project(tmp_path, [
        {"name": "digests", "format": "body", "glob": "digests/*.md"},
    ])
    result = run_hook(
        "--prompt", {"prompt": "rules for running a destructive command"}, root
    )
    context = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
    assert "NEVER run a destructive command" in context


def test_force_pins_a_digest_regardless_of_score(tmp_path):
    digests = tmp_path / "digests"
    digests.mkdir()
    (digests / "release.md").write_text(
        "---\nname: Release policy\ndescription: unrelated wording entirely\n---\n"
        "Tag before you publish.\n",
        encoding="utf-8",
    )
    root = make_project(tmp_path, [
        {"name": "digests", "format": "body", "glob": "digests/*.md",
         "force": {"release": ["ship it"]}},
    ])
    result = run_hook("--prompt", {"prompt": "time to ship it upstream"}, root)
    assert "Tag before you publish" in result.stdout


def test_force_bare_word_does_not_match_a_substring(tmp_path):
    digests = tmp_path / "digests"
    digests.mkdir()
    (digests / "ci.md").write_text(
        "---\nname: CI policy\ndescription: unrelated wording entirely\n---\nRun the suite.\n",
        encoding="utf-8",
    )
    root = make_project(tmp_path, [
        {"name": "digests", "format": "body", "glob": "digests/*.md",
         "force": {"ci": ["ci"]}},
    ])
    # "circle" contains "ci" but must not trigger the bare-word force term.
    result = run_hook("--prompt", {"prompt": "draw a circle around the diagram"}, root)
    assert result.stdout == ""


# --------------------------------------------------------------------------
# 6. init
# --------------------------------------------------------------------------

def test_init_writes_a_usable_config_and_refuses_to_clobber(tmp_path):
    first = subprocess.run([sys.executable, JIT_PY, "--init"],
                           capture_output=True, text=True, cwd=str(tmp_path))
    assert first.returncode == 0
    target = tmp_path / ".flashback" / "jit.json"
    assert json.loads(target.read_text(encoding="utf-8"))["sources"]

    second = subprocess.run([sys.executable, JIT_PY, "--init"],
                            capture_output=True, text=True, cwd=str(tmp_path))
    assert second.returncode == 1
    assert "refusing to overwrite" in second.stderr


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
