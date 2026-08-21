"""Flashback CLI -- thin, additive ergonomic sugar over pins.py's public API.

See reviews/sota-evolution/SYNTHESIS.md item A31. Six of six SOTA-evolution reviewers converged on
"the Bash-CLI invocation is the adoption bottleneck" (C2.1): Opus 5 measured the raw command to
anchor one git branch at ~190 characters and five flags and concluded "the cost of the correct
action exceeds my estimate of the cost of hoping." This file is the cheapest fix that direction
allows without touching anything hardened -- it derives arguments a caller would otherwise have to
compute by hand (the current branch, a file's sha256, whether a path exists) and hands them to
pins.py's EXISTING pin() / unpin() / list_pins() -- unchanged, still the only code that validates a
check, enforces the byte/count budget, or writes to disk.

Deliberately NOT merged into pins.py (compare that file's own module docstring on why IT stays
standalone from tools/session_bus/bus.py, for the same reason): pins.py is the hardened, reviewed
surface (SECURITY HARDENING PASS, 2026-07-30, four independent adversarial reviews, plus the
2026-08-10 SOTA-evolution round this file is itself an output of); this file is unreviewed sugar on
top of it. A bug here can misfire an argparse call or refuse when it should not -- it cannot forge a
pin record, bypass a size cap, or write outside pins.py's STATE_ROOT, because it never touches
storage directly. Every mutation goes through pin()/unpin(), exactly as pins.py's own _cli() drives
them.

Refuses rather than guesses wherever a derivation is not self-evidently correct, per this task's own
brief:
  - `anchor branch` refuses on a failed/absent git AND on a detached HEAD -- `git rev-parse
    --abbrev-ref HEAD` returns the literal string "HEAD" while detached, which would make a
    git_branch check trivially always-true (HEAD stays "HEAD" across every commit while detached),
    not a real anchor on a named branch.
  - `anchor sha` refuses if the file does not exist, is not a regular file, or is bigger than
    pins.py's own MAX_CHECK_FILE_BYTES -- such a file could never be re-verified on a later
    delivery pass either, per pins.py's own _check_file_size_ok() fail-closed gate.
  - `anchor exists` refuses if the path is currently absent, and `anchor gone` refuses if the path
    currently exists. This matters because pins.py's validate_check() checks a check's SHAPE, not
    its truth (SYNTHESIS.md finding B8: it runs the predicate at write time but discards the
    boolean) -- so pin() alone would happily accept and store a checkable pin that is already false,
    which would render as a loud [CHECK FAILED] on the very next delivery pass. Deriving from
    observed reality closes that gap for the two subcommands where it is cheap and unambiguous to
    do so (a stat, not a content read).

Every security property a check can violate -- a path outside the repo root, a symlink TOCTOU, a
control character or forged banner token in a value, the byte/count budget -- is AUTHORITATIVELY
enforced by pin() itself, unchanged, when this file calls it; that boundary is not duplicated here.
One narrow exception, found by actually running this file against this real, populated workspace
(which does have a real `.env`): `anchor exists`/`anchor gone` must stat a path themselves BEFORE
calling pin(), to check the path's CURRENT state matches what is about to be anchored (see
_require_presence()'s docstring) -- and a bare `.exists()` on a secret-shaped path is itself the
"oracle" pins.py's own (private) `_is_secret_shaped_path()` exists to prevent, per that function's
own docstring. So `_looks_secret_shaped()` below is a small, DELIBERATELY NOT-comprehensive local
mirror of pins.py's secret-name patterns, checked before this file's own first filesystem touch on
a path. It is a courtesy narrowing, not the enforcement boundary: even if this local list misses a
pattern, pin()'s own validate_check() still authoritatively refuses it via pins.py's real, more
complete, unmodified pattern list -- one stat call later than ideal, never a security regression
against today's pins.py. Uses only pins.py's PUBLIC surface otherwise (no leading underscore): pin,
unpin, list_pins, PinError, REPO_ROOT, MAX_CHECK_FIELD_LEN, MAX_CHECK_FILE_BYTES. Session-id
resolution (`_self_session_id` below) deliberately duplicates pins.py's own private helper of the
same name rather than importing it -- six lines, low drift risk, and it keeps the public/private
boundary this file is drawn on unambiguous.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pins  # noqa: E402  (path must be set up first; see hooks/pin_deliver.py for the same pattern)


# --------------------------------------------------------------------------------- derivation

def _self_session_id() -> "str | None":
    """Deliberate local mirror of pins.py's own private `_self_session_id()` -- identical env
    vars, identical order. Kept local rather than imported: it is underscore-private in pins.py,
    and this file only relies on pins.py's public surface (see module docstring)."""
    for var in ("CLAUDE_CODE_SESSION_ID", "CLAUDE_SESSION_ID"):
        val = os.environ.get(var)
        if val:
            return val
    return None


def _derive_branch() -> str:
    """Run the exact command pins.py's own _check_git_branch() uses to verify a git_branch check
    (`git rev-parse --abbrev-ref HEAD`), so the pin this derives is true by construction the
    instant it is written. Refuses -- never guesses -- on a missing git binary, a failed or timed
    out invocation, or a detached HEAD (see module docstring for why "HEAD" is refused, not just
    accepted as a branch name)."""
    git_bin = shutil.which("git")
    if not git_bin:
        raise pins.PinError("git not found on PATH -- cannot derive the current branch")
    try:
        result = subprocess.run(
            [git_bin, "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=pins.REPO_ROOT, capture_output=True, text=True, timeout=10,
        )
    except Exception as e:
        raise pins.PinError(f"could not run git ({e}) -- cannot derive the current branch")
    if result.returncode != 0:
        detail = (result.stderr or "").strip()
        raise pins.PinError(
            "`git rev-parse --abbrev-ref HEAD` failed" + (f": {detail}" if detail else "")
            + f" -- is {pins.REPO_ROOT} really a git repo?"
        )
    branch = result.stdout.strip()
    if not branch:
        raise pins.PinError("git returned an empty branch name -- refusing to guess")
    if branch == "HEAD":
        raise pins.PinError(
            "HEAD is detached (not on a named branch) -- check out a branch first; a git_branch "
            "check against the literal string 'HEAD' would be trivially always-true, not a real "
            "anchor (rev-parse --abbrev-ref reports 'HEAD' for every commit while detached)"
        )
    return branch


# Deliberately NOT pins.py's real _SECRET_PATH_PATTERNS (private, and a courtesy pre-check does
# not need the full fnmatch-based list) -- see module docstring for why this exists and what it
# does and does not guarantee.
_SECRET_PATH_HINTS = (".env", ".pem", ".key", "credentials", "id_rsa", "id_ed25519", ".p12",
                      ".pfx", "secret", ".ssh", ".npmrc", ".pypirc", ".netrc", ".kdbx")


def _looks_secret_shaped(raw_path: str) -> bool:
    lowered = raw_path.replace("\\", "/").lower()
    parts = [p for p in lowered.split("/") if p]
    return any(hint in part for part in parts for hint in _SECRET_PATH_HINTS)


def _normalize_repo_relative(raw_path: str) -> str:
    """Validate raw_path is non-empty, not absolute, not secret-shaped, within pins.py's own
    MAX_CHECK_FIELD_LEN, and resolves inside pins.REPO_ROOT -- the same shape pins.py's own
    (private) _check_path_relative() will independently require when this file's check is later
    validated and verified. The secret-shaped check runs BEFORE anything else touches the
    filesystem (see module docstring); everything past that is pure path arithmetic (one
    `.resolve()`, no content read) -- existence is the caller's concern, not this function's.
    Returns the path with forward slashes: Windows accepts these natively, and it keeps the stored
    check.path portable if pins.json is ever read on a POSIX box."""
    if not raw_path:
        raise pins.PinError("path is required")
    if _looks_secret_shaped(raw_path):
        raise pins.PinError(
            f"{raw_path!r} looks like a secret-shaped path -- refusing before even checking "
            f"whether it exists (pin()'s own check would refuse it too; this just avoids "
            f"touching it at all)"
        )
    if Path(raw_path).is_absolute():
        raise pins.PinError(f"path must be repo-relative, not absolute: {raw_path!r}")
    if len(raw_path) > pins.MAX_CHECK_FIELD_LEN:
        raise pins.PinError(
            f"path is {len(raw_path)} chars, over pins.py's own {pins.MAX_CHECK_FIELD_LEN}-char "
            f"check-field limit"
        )
    root = pins.REPO_ROOT.resolve()
    resolved = (pins.REPO_ROOT / raw_path).resolve()
    if resolved != root and root not in resolved.parents:
        raise pins.PinError(f"{raw_path!r} resolves outside the repo root ({root}) -- refusing")
    return raw_path.replace("\\", "/")


def _require_presence(rel_path: str, expect_present: bool) -> None:
    """Stat the path -- existence only, never a content read -- and refuse if its CURRENT state
    does not match what the caller is about to anchor. Necessary because validate_check() checks a
    check's shape, not its truth (SYNTHESIS.md finding B8): without this, `anchor exists` on an
    absent path or `anchor gone` on a present one would both write a checkable pin that is already
    false, which would render as a loud [CHECK FAILED] on the very next delivery pass instead of
    ever showing [CHECK PASSED]. expect_present=True is `anchor exists`, False is `anchor gone`."""
    present = (pins.REPO_ROOT / rel_path).exists()
    if expect_present and not present:
        raise pins.PinError(
            f"no such path: {rel_path!r} -- 'anchor exists' anchors a fact that is true right "
            f"now, not a hoped-for one; use 'anchor gone' if you mean to anchor its current absence"
        )
    if not expect_present and present:
        raise pins.PinError(
            f"path exists: {rel_path!r} -- 'anchor gone' anchors a fact that is true right now, "
            f"not a hoped-for one; use 'anchor exists' if you mean to anchor its current presence"
        )


def _hash_repo_file(raw_path: str) -> "tuple[str, str]":
    """Validate, then read and hash a repo-relative file exactly as pins.py's own (private)
    _check_file_sha256() will later re-derive it (`hashlib.sha256(path.read_bytes()).hexdigest()`)
    -- so the check this writes is true by construction at write time. Refuses, without reading a
    single byte, if the path is absent, not a regular file, or bigger than pins.py's own
    MAX_CHECK_FILE_BYTES -- such a file could never be re-verified on a later delivery pass either,
    per pins.py's own fail-closed _check_file_size_ok() gate, so writing that check would just be
    writing a pin doomed to evict as [CHECK FAILED] the first time anyone delivers it."""
    rel = _normalize_repo_relative(raw_path)
    resolved = pins.REPO_ROOT / rel
    if not resolved.exists():
        raise pins.PinError(f"no such file: {raw_path!r} -- cannot derive a sha256 for a file "
                             f"that does not exist")
    if not resolved.is_file():
        raise pins.PinError(f"not a regular file: {raw_path!r}")
    size = resolved.stat().st_size
    if size > pins.MAX_CHECK_FILE_BYTES:
        raise pins.PinError(
            f"{raw_path!r} is {size} bytes, over pins.py's own {pins.MAX_CHECK_FILE_BYTES}-byte "
            f"content-check limit -- it could never be re-verified on a later delivery pass either"
        )
    digest = hashlib.sha256(resolved.read_bytes()).hexdigest()
    return rel, digest


def _flicker_key(text: str) -> str:
    """Auto-generated flicker key: a short slug of the text (readable in `flashback list`) plus a
    short content hash, so two DIFFERENT flickers never collide on key, while re-flickering the
    IDENTICAL text collapses onto the same key -- pin()'s own keyed upsert then correctly resets
    that fact's compaction-TTL clock instead of piling up near-duplicate flickers."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:24].strip("-") or "note"
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:6]
    return f"flicker-{slug}-{digest}"


def _report(res: dict, as_json: bool, verb: str) -> int:
    """Shared success rendering for every mutating subcommand -- mirrors pins.py's own `pin`
    subcommand output shape (see pins.py's _cli()) so `flashback anchor ...` / `flicker` output
    reads like a natural extension of `pins.py pin`, not a different tool."""
    if as_json:
        print(json.dumps(res, indent=2))
        return 0
    print(f"{verb} [{res['key']}] -- {res['pins']} pin(s), "
          f"{res['usedBytes']}/{res['budget']} bytes used")
    if res["evicted"]:
        print(f"evicted to stay in budget: {', '.join(res['evicted'])}")
    return 0


# ----------------------------------------------------------------------------------- CLI

def _cli() -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="flashback",
        description="Flashback ergonomic CLI -- thin sugar over pins.py's public API. Derives "
                     "arguments where it safely can; refuses rather than guesses where it can't. "
                     "See reviews/sota-evolution/SYNTHESIS.md item A31.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    anchor = sub.add_parser("anchor", help="derive and write a checkable pin (an 'Anchor')")
    anchor_sub = anchor.add_subparsers(dest="anchor_cmd", required=True)

    p = anchor_sub.add_parser("branch", help="anchor the current git branch (git_branch check)")
    p.add_argument("--key", default=None, help="pin key (default: 'branch')")
    p.add_argument("--json", action="store_true")

    p = anchor_sub.add_parser("sha", help="anchor a file's sha256 (file_sha256 check)")
    p.add_argument("path", help="repo-relative path to hash")
    p.add_argument("--key", default=None, help="pin key (default: derived from the filename)")
    p.add_argument("--json", action="store_true")

    p = anchor_sub.add_parser("exists", help="anchor that a path currently exists (path_exists check)")
    p.add_argument("path", help="repo-relative path")
    p.add_argument("--key", default=None, help="pin key (default: derived from the filename)")
    p.add_argument("--json", action="store_true")

    p = anchor_sub.add_parser("gone", help="anchor that a path is currently absent (path_absent check)")
    p.add_argument("path", help="repo-relative path")
    p.add_argument("--key", default=None, help="pin key (default: derived from the filename)")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("flicker", help="write an uncheckable judgment-call pin (a 'Flicker')")
    p.add_argument("text", help="the free-text claim to flicker")
    p.add_argument("--key", default=None, help="pin key (default: auto-generated from the text)")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("list", help="thin alias for `pins.py pins` -- list current pins")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("unpin", help="thin alias for `pins.py unpin` -- remove a pin by key")
    p.add_argument("key")

    args = parser.parse_args()
    sid = _self_session_id()
    if not sid:
        print("ERROR: no session id (set CLAUDE_CODE_SESSION_ID, or run inside a Claude Code "
              "session)", file=sys.stderr)
        return 1

    try:
        if args.cmd == "anchor" and args.anchor_cmd == "branch":
            branch = _derive_branch()
            key = args.key or "branch"
            check = {"type": "git_branch", "expect": branch}
            value = f"on git branch '{branch}'"
            res = pins.pin(sid, key, "checkable", value, check)
            return _report(res, args.json, "anchored")

        if args.cmd == "anchor" and args.anchor_cmd == "sha":
            rel, digest = _hash_repo_file(args.path)
            key = args.key or f"sha-{Path(args.path).name}"
            check = {"type": "file_sha256", "path": rel, "sha256": digest}
            value = f"sha256 of {rel} == {digest}"
            res = pins.pin(sid, key, "checkable", value, check)
            return _report(res, args.json, "anchored")

        if args.cmd == "anchor" and args.anchor_cmd == "exists":
            rel = _normalize_repo_relative(args.path)
            _require_presence(rel, expect_present=True)
            key = args.key or f"exists-{Path(args.path).name}"
            check = {"type": "path_exists", "path": rel}
            value = f"{rel} exists"
            res = pins.pin(sid, key, "checkable", value, check)
            return _report(res, args.json, "anchored")

        if args.cmd == "anchor" and args.anchor_cmd == "gone":
            rel = _normalize_repo_relative(args.path)
            _require_presence(rel, expect_present=False)
            key = args.key or f"gone-{Path(args.path).name}"
            check = {"type": "path_absent", "path": rel}
            value = f"{rel} is absent"
            res = pins.pin(sid, key, "checkable", value, check)
            return _report(res, args.json, "anchored")

        if args.cmd == "flicker":
            text = (args.text or "").strip()
            if not text:
                raise pins.PinError("flicker text must not be empty")
            key = args.key or _flicker_key(text)
            res = pins.pin(sid, key, "uncheckable", text)
            return _report(res, args.json, "flickered")

        if args.cmd == "list":
            res = pins.list_pins(sid)
            if args.json:
                print(json.dumps(res, indent=2))
                return 0
            if not res["pins"]:
                print("no pins")
            for key, rec in res["pins"].items():
                print(f"  [{key}] ({rec['kind']}) {rec['value']}")
            print(f"{res['usedBytes']}/{res['budget']} bytes used")
            return 0

        if args.cmd == "unpin":
            res = pins.unpin(sid, args.key)
            print(f"removed [{res['removed']}] -- {res['pins']} pin(s) left")
            return 0

    except pins.PinError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    return 1


if __name__ == "__main__":
    sys.exit(_cli())
