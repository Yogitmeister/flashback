#!/usr/bin/env python3
"""Flashback JIT -- just-in-time context retrieval. Stdlib-only, fail-open, zero deps.

Flashback asks three questions whenever context might enter a session:

    Is it relevant?   -> this module (JIT retrieval)
    Is it still true? -> pins.py    (checked continuity)
    Is now the time?  -> both, via lifecycle-addressed hooks

This is the relevance half. It scores the current prompt (or the pending tool
call) against corpora you declare in a config file, and injects a few short,
high-scoring pointers instead of loading everything on every turn.

WHAT MAKES IT PORTABLE
----------------------
Nothing about any particular project is compiled in. You declare corpora in
`.flashback/jit.json`; this module knows how to read three shapes:

    "frontmatter"  a directory of Markdown files with YAML frontmatter
                   carrying `name:` and `description:`
    "manifest"     a JSON file listing entries with name/description/file
    "body"         Markdown files whose *body* is injected verbatim when they
                   score high enough (small curated digests -- keep them short)

Run `python jit.py --init` to write a starter config, then `--check` to see
what would be loaded and why.

DESIGN CONSTRAINTS (this runs on the hot path of every prompt and tool call)
---------------------------------------------------------------------------
  * stdlib only   -> no embeddings, no network, no install step
  * fail-open     -> any error exits 0 with no output; never break a prompt
  * cheap         -> reads only the frontmatter head of each file
  * deterministic -> term overlap with idf weighting; identical on every machine
  * toggleable    -> `touch .flashback/jit.off` disables all injection
  * quiet         -> below threshold means no output, not noise

OUTPUT CONTRACT
---------------
JSON on stdout with `hookSpecificOutput.additionalContext` -- the version-safe
way to add context from both UserPromptSubmit and PreToolUse hooks. Anything
else on stdout risks being read as an error by the harness, so every
diagnostic in this file goes to stderr.
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import os
import re
import sys

__all__ = [
    "Config",
    "load_config",
    "load_source",
    "tokenize",
    "idf",
    "weights",
    "score",
    "rank",
    "select",
    "render",
    "main",
]

# --------------------------------------------------------------------------
# Tunables. Overridable globally or per-source in the config file.
# --------------------------------------------------------------------------

DEFAULTS = {
    "min_score": 1.5,          # below this, stay silent
    "min_match_tokens": 2,     # require >=2 distinct shared terms (kills single-word noise)
    "head_bytes": 1200,        # only the frontmatter head is read per file
    "max_body_bytes": 4096,    # cap on an injected "body" digest
    "max_hits": 3,             # per source, unless the source overrides it
}

CONFIG_DIR = ".flashback"
CONFIG_NAME = "jit.json"
OFF_SWITCH = "jit.off"

STOPWORDS = frozenset("""
a an and are as at be been but by can could did do does doing done for from
had has have having he her hers him his how i if in into is it its me more
most my no nor not of off on once only or other our out over own same she
should so some such than that the their them then there these they this
those through to too under until up very was we were what when where which
while who whom why will with would you your
about after again against all also any because before below between both
during each few further here just now s t don ll m o re ve y ain aren couldn
didn doesn hadn hasn haven isn ma mightn mustn needn shan shouldn wasn weren
won wouldn
please help need want make sure let get got go going use using used
""".split())

TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9\-_.]{1,}")
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.S)
SEPARATOR_RE = re.compile(r"[\s./-]")


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

STARTER_CONFIG = {
    "sources": [
        {
            "name": "notes",
            "format": "frontmatter",
            "glob": "docs/notes/*.md",
            "label": "Relevant notes (verify before relying -- may be stale)",
            "max_hits": 3,
        },
        {
            "name": "runbooks",
            "format": "body",
            "glob": ".flashback/digests/*.md",
            "label": "Prompt-relevant operating guidance",
            "max_hits": 2,
        },
    ],
    "min_score": DEFAULTS["min_score"],
    "min_match_tokens": DEFAULTS["min_match_tokens"],
}


class Config:
    """Resolved JIT configuration, rooted at the project directory."""

    def __init__(self, root: str, data: dict):
        self.root = root
        self.data = data or {}
        self.sources = self.data.get("sources") or []
        self.min_score = float(self.data.get("min_score", DEFAULTS["min_score"]))
        self.min_match_tokens = int(
            self.data.get("min_match_tokens", DEFAULTS["min_match_tokens"])
        )
        self.head_bytes = int(self.data.get("head_bytes", DEFAULTS["head_bytes"]))
        self.max_body_bytes = int(
            self.data.get("max_body_bytes", DEFAULTS["max_body_bytes"])
        )

    @property
    def off_switch(self) -> str:
        return os.path.join(self.root, CONFIG_DIR, OFF_SWITCH)

    def is_off(self) -> bool:
        return os.path.exists(self.off_switch)


def find_root(start: str | None = None) -> str | None:
    """Walk up from `start` looking for a .flashback/ directory."""
    cur = os.path.abspath(start or os.getcwd())
    while True:
        if os.path.isdir(os.path.join(cur, CONFIG_DIR)):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent


def load_config(start: str | None = None) -> Config | None:
    """Locate and parse the JIT config; None when JIT is not configured here.

    Precedence: $FLASHBACK_JIT_CONFIG, then the nearest `.flashback/jit.json`
    walking up from `start` (default: cwd).
    """
    explicit = os.environ.get("FLASHBACK_JIT_CONFIG")
    if explicit:
        try:
            with open(explicit, encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception:
            return None
        # <root>/.flashback/jit.json -> <root>
        root = os.path.dirname(os.path.dirname(os.path.abspath(explicit)))
        return Config(root, data)

    root = find_root(start)
    if not root:
        return None
    try:
        with open(os.path.join(root, CONFIG_DIR, CONFIG_NAME), encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        return None
    return Config(root, data)


# --------------------------------------------------------------------------
# Scoring engine
# --------------------------------------------------------------------------

def tokenize(text: str) -> set[str]:
    return {t for t in TOKEN_RE.findall((text or "").lower())
            if t not in STOPWORDS and len(t) > 1}


def read_head(path: str, limit: int) -> str:
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read(limit)


def parse_frontmatter(head: str) -> tuple[str, str]:
    m = re.match(r"^---\s*\n(.*?)\n---", head or "", re.S)
    if not m:
        return "", ""
    fm = m.group(1)
    n = re.search(r"^name:\s*(.+)$", fm, re.M)
    d = re.search(r"^description:\s*(.+)$", fm, re.M)
    return (
        n.group(1).strip().strip("'\"") if n else "",
        d.group(1).strip().strip("'\"") if d else "",
    )


def idf(corpus: list[dict]) -> dict[str, float]:
    """Inverse document frequency over the corpus -- rare terms weigh more."""
    n = max(1, len(corpus))
    df: dict[str, int] = {}
    for item in corpus:
        for tok in item["tokens"]:
            df[tok] = df.get(tok, 0) + 1
    return {tok: math.log(1 + n / c) for tok, c in df.items()}


def weights(corpus: list[dict]) -> dict[str, float]:
    """Per-token match weight: a flat 1.0 floor plus an idf bonus.

    The floor is what makes `min_score` portable. Raw idf is bounded by corpus
    size -- with five documents every token weighs under 1.8, so a threshold
    tuned against a corpus of hundreds silently rejects every match in a small
    one. A newcomer with four notes would conclude the retriever is broken when
    it is only mis-scaled.

    With the floor, `min_score` reads as a count of shared terms (two matches
    clear the 1.5 default) and idf still decides the ordering among them.
    """
    return {tok: 1.0 + w for tok, w in idf(corpus).items()}


def score(query: set[str], item: dict, weights: dict[str, float]) -> tuple[float, int]:
    shared = query & item["tokens"]
    return sum(weights.get(tok, 1.0) for tok in shared), len(shared)


def rank(query: set[str], corpus: list[dict], weights: dict[str, float],
         limit: int, min_score: float, min_match_tokens: int) -> list[tuple[float, dict]]:
    scored = []
    for item in corpus:
        s, n = score(query, item, weights)
        if s >= min_score and n >= min_match_tokens:
            scored.append((s, item))
    # Score first, then name: identical scores must resolve the same way on
    # every machine, or two developers see different context for one prompt.
    scored.sort(key=lambda x: (-x[0], x[1].get("name", "")))
    return scored[:limit]


# --------------------------------------------------------------------------
# Source loaders -- one per declared `format`
# --------------------------------------------------------------------------

def _resolve_glob(cfg: Config, pattern: str) -> list[str]:
    if not pattern:
        return []
    if os.path.isabs(pattern):
        return sorted(glob.glob(pattern, recursive=True))
    return sorted(glob.glob(os.path.join(cfg.root, pattern), recursive=True))


def _rel(cfg: Config, path: str) -> str:
    try:
        return os.path.relpath(path, cfg.root).replace("\\", "/")
    except ValueError:          # different drive on Windows
        return path.replace("\\", "/")


def _load_frontmatter_source(cfg: Config, src: dict) -> list[dict]:
    out = []
    skip = set(src.get("skip") or [])
    for path in _resolve_glob(cfg, src.get("glob", "")):
        base = os.path.basename(path)
        if base in skip:
            continue
        try:
            name, desc = parse_frontmatter(read_head(path, cfg.head_bytes))
        except Exception:
            continue
        stem = os.path.splitext(base)[0]
        out.append({
            "name": name or stem,
            "slug": stem,
            "desc": desc,
            "path": _rel(cfg, path),
            "tokens": tokenize(f"{name} {desc} {stem.replace('_', ' ').replace('-', ' ')}"),
        })
    return out


def _load_manifest_source(cfg: Config, src: dict) -> list[dict]:
    """A JSON manifest of entries. `entries_path` is a dotted path into the
    document; omit it when the document is already a list."""
    path = src.get("path", "")
    if not path:
        return []
    full = path if os.path.isabs(path) else os.path.join(cfg.root, path)
    try:
        with open(full, encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        return []

    node = data
    for key in filter(None, (src.get("entries_path") or "").split(".")):
        node = node.get(key) if isinstance(node, dict) else None
        if node is None:
            return []

    entries: list = []
    if isinstance(node, list):
        entries = node
    elif isinstance(node, dict):
        # Accept {id: entry} and {group: {"items": [...]}} alike.
        for value in node.values():
            if isinstance(value, dict) and isinstance(value.get("items"), list):
                entries.extend(value["items"])
            elif isinstance(value, dict):
                entries.append(value)

    name_key = src.get("name_key", "name")
    desc_key = src.get("desc_key", "description")
    ref_key = src.get("ref_key", "file")

    out = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get(name_key) or "")
        desc = str(entry.get(desc_key) or "")
        ref = str(entry.get(ref_key) or "")
        if not (name or desc):
            continue
        stem = os.path.splitext(os.path.basename(ref))[0]
        out.append({
            "name": name or stem,
            "slug": stem,
            "desc": desc,
            "path": ref.replace("\\", "/"),
            "tokens": tokenize(f"{name} {desc} {stem.replace('-', ' ')}"),
        })
    return out


def _load_body_source(cfg: Config, src: dict) -> list[dict]:
    """Small curated digests whose body is injected verbatim on a strong match."""
    out = []
    aliases = src.get("aliases") or {}
    for path in _resolve_glob(cfg, src.get("glob", "")):
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                raw = fh.read(cfg.max_body_bytes)
        except Exception:
            continue
        match = FRONTMATTER_RE.match(raw)
        if match:
            name, desc = parse_frontmatter(raw)
            body = match.group(2).strip()
        else:
            name, desc, body = "", "", raw.strip()
        if not body:
            continue
        slug = os.path.splitext(os.path.basename(path))[0]
        alias_text = " ".join(aliases.get(slug, []))
        out.append({
            "name": name or slug,
            "slug": slug,
            "desc": desc,
            "body": body,
            "path": _rel(cfg, path),
            "tokens": tokenize(
                f"{name} {desc} {slug.replace('-', ' ')} {alias_text} {body}"
            ),
        })
    return out


LOADERS = {
    "frontmatter": _load_frontmatter_source,
    "manifest": _load_manifest_source,
    "body": _load_body_source,
}


def load_source(cfg: Config, src: dict) -> list[dict]:
    loader = LOADERS.get(src.get("format", "frontmatter"))
    if not loader:
        return []
    try:
        return loader(cfg, src)
    except Exception:
        return []


# --------------------------------------------------------------------------
# Selection and rendering
# --------------------------------------------------------------------------

def _forced_slugs(src: dict, query: set[str], lower_text: str) -> set[str]:
    """`force` pins an entry into context regardless of score.

    A term containing a separator is matched against the raw text; a bare word
    must appear as a whole token, so "ci" never fires on "circle".
    """
    forced = set()
    for slug, terms in (src.get("force") or {}).items():
        for term in terms:
            term_l = str(term).lower()
            hit = term_l in lower_text if SEPARATOR_RE.search(term_l) else term_l in query
            if hit:
                forced.add(slug)
                break
    return forced


def select(cfg: Config, query: set[str], text: str = "") -> list[tuple[dict, list]]:
    """Return [(source, hits)] for every configured source with a match."""
    results = []
    lower = (text or "").lower()
    for src in cfg.sources:
        corpus = load_source(cfg, src)
        if not corpus:
            continue
        limit = int(src.get("max_hits", DEFAULTS["max_hits"]))
        hits = rank(
            query, corpus, weights(corpus), limit,
            float(src.get("min_score", cfg.min_score)),
            int(src.get("min_match_tokens", cfg.min_match_tokens)),
        ) if len(query) >= 2 else []

        forced_slugs = _forced_slugs(src, query, lower)
        if forced_slugs:
            seen = {h[1].get("slug") for h in hits}
            forced = [(99.0, item) for item in corpus
                      if item.get("slug") in forced_slugs and item.get("slug") not in seen]
            forced.sort(key=lambda x: x[1].get("slug") or "")
            hits = (forced + hits)[:limit]

        if hits:
            results.append((src, hits))
    return results


def render(results: list[tuple[dict, list]]) -> str:
    lines: list[str] = []
    for src, hits in results:
        label = src.get("label") or src.get("name", "Relevant context")
        lines.append(f"{label}:")
        if src.get("format") == "body":
            for _, item in hits:
                lines.append(f"--- {item.get('slug') or item['name']} ---")
                lines.append(item["body"])
        else:
            for _, item in hits:
                path = item.get("path") or ""
                suffix = f" [{path}]" if path else ""
                lines.append(f"  - {item['name']}: {item.get('desc') or ''}{suffix}".rstrip())
    return "\n".join(lines).strip()


def emit(additional_context: str, event: str) -> None:
    """Print the hook JSON that injects additional_context, then exit 0."""
    if additional_context.strip():
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": event,
            "additionalContext": additional_context,
        }}))
    sys.exit(0)


def read_stdin_json() -> dict:
    try:
        raw = sys.stdin.read()
    except Exception:
        return {}
    if not raw or not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


# --------------------------------------------------------------------------
# Modes
# --------------------------------------------------------------------------

def query_text_for_tool(payload: dict) -> str:
    """Build a query from a pending tool call: its target plus its arguments."""
    inp = payload.get("tool_input")
    inp = inp if isinstance(inp, dict) else {}
    parts = [str(payload.get("tool_name") or "")]
    for key in ("file_path", "path", "notebook_path", "command",
                "pattern", "query", "url"):
        value = inp.get(key)
        if isinstance(value, str) and value:
            parts.append(value)
    # Split every identifier separator into whitespace. A pending edit to
    # "db/migration/0002_add_rules.sql" should match a note about migration
    # rules; left intact, "0002_add_rules.sql" is one opaque token that matches
    # nothing. Filenames are the main signal in tool mode, so they have to be
    # broken into words the corpus can actually share.
    return re.sub(r"[\\/_.\-]+", " ", " ".join(parts))


def _run(text: str, event: str) -> None:
    cfg = load_config()
    if cfg is None or not cfg.sources or cfg.is_off():
        sys.exit(0)
    query = tokenize(text)
    if len(query) < 2:
        sys.exit(0)
    emit(render(select(cfg, query, text)), event)


def mode_prompt() -> None:
    text = str(read_stdin_json().get("prompt") or "")
    if not text.strip():
        sys.exit(0)
    _run(text, "UserPromptSubmit")


def mode_tool() -> None:
    text = query_text_for_tool(read_stdin_json())
    if not text.strip():
        sys.exit(0)
    _run(text, "PreToolUse")


def mode_check(text: str | None) -> int:
    """Diagnostics on stderr -- never pollutes the hook stdout contract."""
    cfg = load_config()
    if cfg is None:
        print("flashback jit: no .flashback/jit.json found (walked up from cwd).\n"
              "Run `python jit.py --init` to create one.", file=sys.stderr)
        return 1
    print(f"root:       {cfg.root}", file=sys.stderr)
    print(f"config:     {os.path.join(cfg.root, CONFIG_DIR, CONFIG_NAME)}", file=sys.stderr)
    print(f"off:        {cfg.is_off()}  ({cfg.off_switch})", file=sys.stderr)
    print(f"thresholds: min_score={cfg.min_score} "
          f"min_match_tokens={cfg.min_match_tokens}", file=sys.stderr)
    if not cfg.sources:
        print("  warning: no sources configured", file=sys.stderr)
    for src in cfg.sources:
        corpus = load_source(cfg, src)
        print(f"  source {src.get('name', '?')!r} "
              f"[{src.get('format', 'frontmatter')}] -> {len(corpus)} entries",
              file=sys.stderr)
        if not corpus:
            target = src.get("glob") or src.get("path") or "(unset)"
            print(f"    warning: nothing matched {target!r}", file=sys.stderr)
    if text:
        query = tokenize(text)
        print(f"\nquery tokens ({len(query)}): {' '.join(sorted(query))}", file=sys.stderr)
        print("\n--- would inject ---", file=sys.stderr)
        print(render(select(cfg, query, text)) or "(nothing -- below threshold)",
              file=sys.stderr)
    return 0


def mode_init(force: bool) -> int:
    root = find_root() or os.getcwd()
    target_dir = os.path.join(root, CONFIG_DIR)
    target = os.path.join(target_dir, CONFIG_NAME)
    if os.path.exists(target) and not force:
        print(f"refusing to overwrite {target} (pass --force)", file=sys.stderr)
        return 1
    os.makedirs(target_dir, exist_ok=True)
    with open(target, "w", encoding="utf-8") as fh:
        json.dump(STARTER_CONFIG, fh, indent=2)
        fh.write("\n")
    print(f"wrote {target}", file=sys.stderr)
    print("Edit the `sources` list, then run:\n"
          "  python jit.py --check --text 'a prompt you would actually type'",
          file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="flashback-jit",
        description="Just-in-time context retrieval for AI coding sessions.",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--prompt", action="store_true",
                       help="UserPromptSubmit hook mode; reads hook JSON on stdin")
    group.add_argument("--tool", action="store_true",
                       help="PreToolUse hook mode; reads hook JSON on stdin")
    group.add_argument("--check", action="store_true",
                       help="show what is configured and what a query would inject")
    group.add_argument("--init", action="store_true",
                       help="write a starter .flashback/jit.json")
    parser.add_argument("--text", help="query text for --check")
    parser.add_argument("--force", action="store_true",
                        help="allow --init to overwrite an existing config")
    args = parser.parse_args(argv)

    if args.check:
        return mode_check(args.text)
    if args.init:
        return mode_init(args.force)
    if args.prompt:
        mode_prompt()
    if args.tool:
        mode_tool()
    return 0


if __name__ == "__main__":
    # Fail-open is the whole contract: a retriever that breaks a prompt is far
    # worse than one that returns nothing. The diagnostic modes still raise,
    # because there the error IS the output the operator asked for.
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        if "--check" in sys.argv or "--init" in sys.argv:
            raise
        sys.exit(0)
