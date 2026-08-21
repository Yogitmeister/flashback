<p align="center">
  <img src="docs/cover.png" alt="Flashback" width="1000">
</p>

<h1 align="center">Flashback</h1>

<p align="center"><strong>The right context. Right when it matters. Still true.</strong></p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.9%2B-blue" alt="python 3.9+">
  <img src="https://img.shields.io/badge/dependencies-none-brightgreen" alt="zero dependencies">
  <img src="https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey" alt="platforms">
  <img src="https://img.shields.io/badge/license-Apache--2.0-blue" alt="Apache-2.0 license">
</p>

---

Long agent sessions fail in two directions at once. They carry too much — every rule, every note,
every past decision, loaded on every turn until the useful signal is a rounding error. And they
carry it too long — a branch name, a file path, a "we decided X" that quietly stopped being true an
hour ago, still being repeated with total confidence.

Flashback is a context-admission layer that asks three questions before anything enters a session:

| | Question | What it does |
|---|---|---|
| **Relevance** | Does this help the action happening right now? | Score, threshold, cap, and inject a few items — not the whole corpus |
| **Truth** | Is the retained claim still valid? | Re-derive it from live state; label or expire it when it no longer holds |
| **Timing** | Is this the right moment? | Address context to a lifecycle point — a prompt, a tool call, a compaction |

Two loops, one product. **Just-in-time retrieval** ([`jit.py`](jit.py)) answers relevance and
timing. **Checked continuity** ([`pins.py`](pins.py)) answers truth, and survives compaction.

> A stale memory that reads as canonical is worse than a lossy summary that reads as vague. The
> lossy one invites a second look. The stale one doesn't.

## Use cases

**Your agent keeps forgetting the one thing it must not forget.**
Anchor it. `pins.py` re-derives the fact from live state on every delivery, so after a compaction
your session is told "you are on `wip/checkout-v2`" because it just checked — not because a
summarizer was asked nicely to preserve a sentence.

**Your agent confidently repeats something that stopped being true.**
An Anchor whose check fails does not get quietly re-served. It reports that it changed. This is the
failure mode ordinary memory files cannot catch: they preserve prose, and prose cannot notice that
the world moved.

**Your `CLAUDE.md` has grown into a wall nobody reads — including the model.**
Move the situational parts into a corpus and let Flashback inject only what scores against the
current prompt. Your always-on doctrine gets smaller; your situational guidance gets more relevant.

**A specific kind of edit needs a specific rule.**
Point the JIT retriever at your notes and it fires on the *pending tool call*, not just the prompt.
An edit to `db/migrations/0002_add_index.sql` can surface your migration rules before the write
happens, without those rules occupying context during the other ninety turns.

**You want the decision, not the transcript, to survive compaction.**
Flicker the judgment call. It is delivered once across the boundary, marked unverified, and then
dropped — because nothing can mechanically confirm a judgment, and pretending otherwise is how a
guess hardens into a fact.

**You are running many sessions and want the guidance to travel.**
Corpora are plain files in your repo. Every session in that project gets the same admission rules,
and a teammate cloning it gets them too.

## Quickstart

Nothing to install. Zero dependencies, Python 3.9+.

### The relevance half

```bash
python jit.py --init                       # writes .flashback/jit.json
python jit.py --check --text "how do I deploy staging"
```

`--check` prints what is configured, what matched, and what would be injected — all on stderr, so
it never disturbs the hook contract. Then register it as a hook:

```json
{
  "hooks": {
    "UserPromptSubmit": [
      { "hooks": [{ "type": "command", "command": "python /path/to/jit.py --prompt" }] }
    ],
    "PreToolUse": [
      { "hooks": [{ "type": "command", "command": "python /path/to/jit.py --tool" }] }
    ]
  }
}
```

### The truth half

```bash
# Anchor a mechanical fact -- re-verified fresh every time it is delivered
python pins.py pin --key branch --kind checkable \
    --value "on wip/my-feature" --check-type git_branch --check-arg expect=wip/my-feature

# Flicker a judgment call -- shown once across a compaction, then dropped
python pins.py pin --key next --kind uncheckable \
    --value "next: run the migration, then re-run the test suite"

python pins.py pins        # see what is pinned; no side effects
python install.py          # register the PreCompact and SessionStart hooks (idempotent)
```

After `install.py`, start a new session — hook config is read at session start, not live.

## Configuring retrieval

Everything lives in `.flashback/jit.json`. Nothing about any particular project is compiled into the
code; you describe your corpora and Flashback reads them.

```json
{
  "sources": [
    {
      "name": "notes",
      "format": "frontmatter",
      "glob": "docs/notes/*.md",
      "label": "Relevant notes (verify before relying)",
      "max_hits": 3
    },
    {
      "name": "runbooks",
      "format": "body",
      "glob": ".flashback/digests/*.md",
      "label": "Operating guidance for this action",
      "max_hits": 2,
      "force": { "release-policy": ["ship it", "cut a release"] }
    }
  ]
}
```

Three source shapes cover most projects:

| `format` | Reads | Injects |
|---|---|---|
| `frontmatter` | A directory of Markdown with `name:` / `description:` frontmatter | A one-line pointer per hit |
| `manifest` | A JSON file listing entries (`name`, `description`, `file`) | A one-line pointer per hit |
| `body` | Small curated Markdown digests | The body, verbatim |

Use `frontmatter` and `manifest` for pointers — "this note exists, read it if relevant." Use `body`
for short rules the model should simply *have*. Keep `body` digests small; they are injected in
full.

`force` pins an entry regardless of score, for the cases where a phrase must always pull a rule in.
A force term containing a separator matches the raw text; a bare word must match a whole token, so
`"ci"` never fires on "circle".

**Tuning.** `min_score` reads as a count of shared terms (the 1.5 default clears at two matches) and
rarer terms rank higher. Raise it if you see noise, lower it if you see silence, and use `--check`
against a prompt you would actually type rather than guessing.

**Turning it off.** `touch .flashback/jit.off` disables all injection without touching config.

### Design constraints

This runs on the hot path of every prompt and every tool call, so:

- **stdlib only** — no embeddings, no network, no install step, no model call
- **fail-open** — any error exits 0 with no output; a retriever that breaks a prompt is worse than
  one that returns nothing
- **cheap** — only the frontmatter head of each file is read
- **deterministic** — term overlap with idf weighting, identical on every machine; two developers
  running the same prompt get the same context
- **quiet** — below threshold means no output, not noise

## Why not a memory file, or a vector store

`CLAUDE.md`, a checkpoint, a `SESSION_STATE.md` — these are prose a summarizer is *instructed* to
preserve. An Anchor is not preserved prose; it is re-derived from live state on every delivery. If
the branch changed, the file was deleted, or the config line was reverted, the next delivery says
so, loudly.

Semantic search solves a different half. It retrieves something related. It does not tell you
whether the item is still fresh, whether it belongs before this tool call rather than on every
prompt, or when it should disappear.

| System | Retrieves by relevance | Re-checks live facts | Targets lifecycle timing | Primary scope |
|---|---|---|---|---|
| **Flashback** | **Yes, bounded JIT loop** | **Yes, for Anchors** | **Explicit hooks are the target contract** | One session |
| mem0 | Yes | Not generally | Application-triggered | Cross-session memory |
| MemGPT / Letta | Memory-tier policy | Not generally | Agent-managed | Persistent agent memory |
| LangChain / LlamaIndex memory | Depends on retriever | Not generally | Chain callbacks | Application memory |
| MCP `server-memory` | Store/query dependent | No live predicate check | Caller-triggered | Shared knowledge graph |
| `CLAUDE.md` / skills | No — always-on or on demand | Human-maintained | Session start | Static doctrine |

The closest prior art for the truth half is cache revalidation (`ETag`), `make`-style staleness
checking, and truth-maintenance systems. Flashback adds the question those systems never face:
which verified or unverified item deserves scarce model context, at this exact moment?

## Terminology

**A flashback** is a small context record carrying relevance, truth-state, and lifecycle metadata.
The continuity code calls its stored unit a "pin". Two kinds exist:

| Talk about it as | Internally | Lasts | Because |
|---|---|---|---|
| **Anchor** | `checkable` | As long as it keeps checking out — no TTL | It is a mechanically verifiable fact (a branch, a hash, a path). Re-checked on every delivery, so it never goes stale silently. |
| **Flicker** | `uncheckable` | One compaction, then dropped | It is a judgment call. Nothing can confirm it mechanically, so it is deliberately short-lived rather than trusted forever. |

`checkable` pins draw from a fixed check vocabulary — `path_exists`, `path_absent`, `text_in_file`,
`file_sha256`, `git_branch`, `git_head_prefix`. There is deliberately **no arbitrary-command check
type**: that would be a durable RCE primitive plantable by prompt injection. See `SECURITY.md`.

## Three products. Three powers, kept apart.

| Product | Answers | Owns | Never grants by itself |
|---|---|---|---|
| [Gossip](https://github.com/Yogitmeister/gossip) | Who is running, and what was said? | Correspondence, discovery, observation, history, receipts | Context admission or terminal authority |
| **Flashback** | What belongs in context now, and is it still true? | JIT retrieval, lifecycle timing, freshness, expiry, checked continuity | Permission to act |
| [Agency](https://github.com/Yogitmeister/agency) | Who may command this terminal? | PTY custody, command policy, descendant scope, input receipts | Work scheduling or orchestration |

> **A message is not a memory. A memory is not permission.**

Each is independent and useful alone. Together they keep three powers separate: Gossip knows the
fleet, Flashback decides what enters context, Agency acts. No automatic bridge turns correspondence
into context, or context into a command. Flashback is the middle one — Gossip may surface a claim,
but a message is not evidence, and relevant context is still not permission.

**What that separation is, precisely.** These are product boundaries enforced by capability: Gossip
ships no execution path, Flashback ships no way to command a terminal, Agency ships no interface to
write your context. They are *not* OS isolation. All three run as you, as your user, with your
filesystem. They protect against accidental authority creep and origin confusion between
cooperating tools — not against a hostile process already running under your account.

## Installing

```bash
python install.py              # idempotent -- safe to re-run
python install.py --dry-run    # preview, writes nothing
python install.py --verify     # exit 0 if fully installed
python install.py --uninstall  # removes only Flashback's hook entries, NOT stored pin state
```

Writes to `.claude/settings.local.json`, never a git-tracked settings file — a hook registration is
a machine-local decision. Every path derives from `install.py`'s own location and `sys.executable`,
so cloning this repo anywhere and running it registers correctly wherever it landed.

## Tests

```bash
python -m pytest tests/ -q
```

## Limitations, security, and threat model

Read [`THREAT_MODEL.md`](THREAT_MODEL.md) and [`SECURITY.md`](SECURITY.md) before relying on this
beyond what it claims. In one line: **Flashback is a fidelity mechanism, not a security boundary.**
It reduces the structural attack surface of a durable, re-injected annotation. It does not sandbox,
authorize, coordinate across sessions, or store secrets.

Specifically, it is **not**:

- a way to partition or protect a region of the context window (no such API exists in any
  transformer harness — admission can place material nearer the action, but nothing forces
  attention);
- a source-of-truth database;
- exactly-once delivery — an interrupted process can in principle lose a delivery;
- prompt-injection-proof — the structural surface is reduced, not eliminated;
- cross-session or cross-provider. Each session's pins are its own. That boundary is deliberate:
  sharing context across sessions is a different trust decision, and it belongs to a different
  product.

Built and reviewed against a single-user workspace on trusted repository content.
`THREAT_MODEL.md` section 8 documents exactly what changes under untrusted-content, multi-user, or
CI deployment.

## Status

Alpha, and dogfooded daily. The checked-continuity half has been running in production use on the
author's workspace for months. The JIT half was generalized out of that same workspace for this
release: the engine is the proven one, but its configuration surface is new, and the source shapes
have had far less exposure than `pins.py`. Expect the config schema to gain fields; the hook
contract and CLI are stable.

Issues and pull requests welcome. See [`CONTRIBUTING.md`](CONTRIBUTING.md).

## License

[Apache License 2.0](LICENSE). See [`NOTICE`](NOTICE).

---

<p align="center"><em>Relevant, timely, and still true — or it does not get in.</em></p>
