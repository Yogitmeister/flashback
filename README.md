# Flashback

**The right context. Right when it matters. Still true.**

Flashback is a safe context-admission layer for long-running agent sessions. It combines two loops
that ordinary memory systems treat separately:

1. **Just-in-time context:** retrieve a small, relevant slice for the current prompt, tool, phase,
   or lifecycle hook instead of loading everything on every turn.
2. **Checked continuity:** re-observe the load-bearing facts that must survive compaction and mark
   judgments as unverified or expired instead of repeating them as truth.

Compaction is one high-risk moment, not the whole product. Flashback asks three questions whenever
context might enter a session: **Is it relevant? Is it still true? Is now the right time?**

**Implementation status:** the checked-continuity core in this directory is working, tested,
installed, and dogfooded daily. This workspace also runs a bounded, fail-open JIT retriever from
`tools/jit_context.py` for prompt and tool hooks. They are proven separately but not yet packaged
behind one public Flashback install. Lifecycle-addressable records are the next contract, not a
claim that the current `pins.py` CLI already supports every phase and hook below. Flashback has not
yet been extracted to its own public repository.

## The product model

| Dimension | Flashback question | Safety behavior |
|---|---|---|
| Relevance | Does this context help the present action? | Threshold, rank, cap, and deduplicate before injection |
| Truth freshness | Is the retained claim still valid? | Re-check an Anchor; label or expire an uncheckable Flicker |
| Lifecycle timing | Is this the right moment to admit it? | Address to an explicit phase or hook; default to deterministic events |

The safe first lifecycle vocabulary is mechanical: `next-prompt`, `pre-tool:<tool>`, `pre-compact`,
`post-compact`, and `manual`. `planning` and `implementing` can be explicit session tags or soft
filters. Model-inferred phase classification must not become a security decision in v1.

## The Three Amigents

Three specialists, one safer agent runtime. Each amigo answers a different question and stops at a
different trust boundary.

| Product | The question it answers | Owns | Stops at |
|---|---|---|---|
| [Gossip](https://github.com/Yogitmeister/gossip) | Who is active, and what happened? | Correspondence, discovery, observation, search, messages, history, and receipts | A message is not trusted context |
| **Flashback** | What belongs in this session now, and is it still true? | Safe JIT context, lifecycle timing, freshness, expiry, and checked continuity through compaction | Relevant context is not permission to act |
| Agency | Who may command this terminal? | PTY custody, slash-command policy, descendant scope, and input receipts | Custody is not orchestration or context relevance |

Gossip may find it. Agency may act on it. **Flashback is the trust-bearing middle:** it decides
which evidence belongs in the present session, when to deliver it, and whether it has gone stale.
The three compose without collapsing their authority boundaries.

> **A message is not a memory. A memory is not permission.**

tmux can keep panes and processes alive underneath the trio. It does not provide agent discovery,
checked context admission, or custody-aware self-command. No Invisible Swordsman, no mystery
orchestrator: each amigo has one explicit contract.

> “Gossip carries the correspondence, Agency guards the terminal, Flashback holds the memory: all
> for one, and one memory for all.”
>
> — Mr. Funnyman, consulted with the full technical brief

## Quickstart

```bash
# Anchor a mechanical fact -- re-verified fresh every time it's delivered
python "My Projects/Flashback/pins.py" pin --key branch --kind checkable \
    --value "on wip/my-feature" --check-type git_branch --check-arg expect=wip/my-feature

# Flicker a judgment call -- shown once, then flagged unverified after one compaction, then dropped
python "My Projects/Flashback/pins.py" pin --key next --kind uncheckable \
    --value "next: run the migration, then re-run the test suite"

python "My Projects/Flashback/pins.py" pins     # see what's pinned, no side effects
python "My Projects/Flashback/install.py"       # register the two hooks (idempotent)
```

That's it for checked continuity: `PreCompact` and `SessionStart` hooks handle verification and
re-delivery automatically. The JIT loop is currently installed separately at workspace level.

## Why not just a memory file or a vector search

`CLAUDE.md`, a checkpoint, a `SESSION_STATE.md` -- all of these are prose a summarizer is *instructed*
to preserve. Flashback's checkable half (an "Anchor") is not preserved prose; it's a fact re-derived
from live state on every delivery. If the branch changed, the file got deleted, or the config line got
reverted, the next delivery says so -- loudly -- instead of confidently repeating something that
stopped being true an hour ago. A stale memory that reads as canonical is worse than a lossy summary
that reads as vague, because the lossy one invites a second look and the stale one doesn't.

Semantic search solves a different half of the problem: it can retrieve something related. It does
not automatically say whether the item is fresh, whether it belongs before this tool call rather
than every prompt, or when it should disappear. Flashback's unique value is the combination of
relevance, truth state, and lifecycle timing.

## How it compares

| System | Retrieves by relevance | Re-checks live facts | Targets lifecycle timing | Primary scope |
|---|---|---|---|---|
| **Flashback** | **Yes, bounded JIT loop** | **Yes, for Anchors** | **Explicit hooks/phases are the target contract** | One session today |
| mem0 | Yes | Not generally | Application-triggered retrieval | Cross-session memory |
| MemGPT / Letta | Memory-tier policy | Not generally | Agent-managed memory operations | Persistent agent memory |
| LangChain / LlamaIndex memory | Depends on retriever | Not generally | Chain/application callbacks | Application memory |
| MCP `server-memory` | Store/query dependent | No built-in live predicate check | Caller-triggered | Shared knowledge graph |
| `CLAUDE.md` / skills | No—always/on demand by harness | Human-maintained | Session start or skill invocation | Static doctrine |

The closer intellectual prior art for checked continuity is cache revalidation (`ETag`),
`make`-style staleness checking, and truth-maintenance systems. Flashback adds the admission-control
question those systems do not face: which verified or unverified item should enter a scarce model
context at this exact lifecycle point?

**What the current directory implements precisely:** a harness-light invariant ledger that
re-observes a small set of workspace predicates after compaction. **What the Flashback product now
encompasses:** that ledger plus the workspace's bounded JIT context loop and the lifecycle-addressing
contract needed to unify them.

**What it is not, and does not claim to be:** a way to partition or protect a region of the context
window itself (no such API exists in any transformer harness); a source-of-truth database;
cross-provider today (verified for Claude Code CLI and Nimbalyst-hosted sessions on provider `claude-code` only --
see `knowledge/products/flashback/README.md` in the parent workspace for that verification);
exactly-once delivery (an interrupted process can, in principle, lose a delivery -- see
`THREAT_MODEL.md`); prompt-injection-proof (the structural attack surface is reduced, not eliminated --
see `SECURITY.md`); or "flat fidelity across arbitrarily many compactions" without the qualification
that delivery, relevance, and predicate semantics all have their own limits, documented below and in
`DESIGN.md`.

## Terminology

**A flashback** is a small context record with relevance, truth-state, and lifecycle metadata. The
current continuity code calls its stored unit a "pin"; two kinds exist today, distinguished by how
long they last and why:

| Talk about it as... | Internally (`kind`) | Lasts... | Because... |
|---|---|---|---|
| **Anchor** | `checkable` | as long as it keeps checking out -- no TTL | a mechanically verifiable fact (a branch name, a file's hash, a path). Re-checked fresh on every delivery, so it never goes stale silently. |
| **Flicker** | `uncheckable` | one compaction, by design -- then dropped | a judgment call, not a checkable fact. Nothing can mechanically confirm it, so it's deliberately short-lived rather than trusted forever. |

Full rationale, the "staleness beats loss" problem this solves, and the complete 2026-07-30 security
hardening pass are in `DESIGN.md` -- this file is the practical reference, not a duplicate.

## Installing (in this repo, or a clone/extraction of it)

```bash
python "My Projects/Flashback/install.py"              # idempotent -- safe to re-run
python "My Projects/Flashback/install.py" --dry-run     # preview, writes nothing
python "My Projects/Flashback/install.py" --verify      # exit 0 if fully installed
python "My Projects/Flashback/install.py" --uninstall   # removes only Flashback's own hook entries -- NOT stored pin state, see SECURITY.md
```

Writes to `.claude/settings.local.json`, never the git-tracked `.claude/settings.json` -- a hook
registration is a machine-local decision (`DESIGN.md` section 3.4). Every path is derived from
`install.py`'s own location and `sys.executable`, not hardcoded to one machine -- running it after
cloning this repo elsewhere registers correctly wherever it landed. **After installing:** start a new
Claude Code session (or restart) in this repo -- hook config is read at session start, not live.

## CLI (agent-facing)

Requires `CLAUDE_CODE_SESSION_ID` in the environment, which every Claude Code Bash tool call already
has.

```bash
python "My Projects/Flashback/pins.py" pin --key branch --kind checkable \
    --value "on wip/flashback-design" --check-type git_branch --check-arg expect=wip/flashback-design

python "My Projects/Flashback/pins.py" pin --key decision --kind uncheckable \
    --value "ship the narrow checkable-pin design, not the full KV store"

python "My Projects/Flashback/pins.py" pins
python "My Projects/Flashback/pins.py" unpin --key decision
python "My Projects/Flashback/pins.py" deliver     # MUTATES STATE -- verify+render now, for manual testing; not a preview
```

`checkable` pins require `--check-type` from the fixed vocabulary in `DESIGN.md` section 4.3
(`path_exists`, `path_absent`, `text_in_file`, `file_sha256`, `git_branch`, `git_head_prefix`) --
there is no arbitrary-command check type, by design (`DESIGN.md` section 2, `SECURITY.md`). Both `key`
and `value` are single-line only and cannot contain this system's own rendered-banner markers -- a
value is later re-injected into your own context, and it must never be able to forge a fake
instruction line.

## Manually testing the hooks (useful for debugging even though they're now registered)

```bash
SID="whatever-id"

# 1. pin something (see CLI above)

# 2. simulate a compaction boundary
echo '{"hook_event_name":"PreCompact","session_id":"'"$SID"'","trigger":"manual"}' | \
    python "My Projects/Flashback/hooks/pin_precompact.py"

# 3. simulate the session resuming and see the re-injected pins
echo '{"hook_event_name":"SessionStart","session_id":"'"$SID"'"}' | \
    python "My Projects/Flashback/hooks/pin_deliver.py"

# 4. simulate another tool call in the same generation -- should print nothing (already delivered)
echo '{"hook_event_name":"PostToolUse","session_id":"'"$SID"'"}' | \
    python "My Projects/Flashback/hooks/pin_deliver.py"
```

Run this exact sequence with `CLAUDE_CONFIG_DIR` pointed at a throwaway directory first if you don't
want to touch real state (`~/.claude/flashback/pins/<session_id>.json` otherwise).

## Tests

```bash
python -m pytest "My Projects/Flashback/tests/" -q
```

## Limitations, security, and threat model

Read `THREAT_MODEL.md` and `SECURITY.md` before relying on this for anything beyond what it actually
claims. In one line: **Flashback is a fidelity mechanism, not a security boundary.** It reduces the
structural attack surface of a durable, re-injected annotation; it does not sandbox, authorize,
coordinate across sessions, or store secrets, and it was built and reviewed against a single-user
workspace on trusted repository content -- `THREAT_MODEL.md` section 8 documents exactly what changes
under an untrusted-content, multi-user, or CI deployment.

## What's deliberately NOT here

- No heuristic creation of durable pins -- Anchors and Flickers remain agent-initiated
  (`DESIGN.md` section 4.7). The separate JIT loop ranks registered context sources; it does not
  silently promote retrieved text into durable truth.
- No protected region inside the transformer context window. JIT admission can place relevant
  material nearer the action and checked continuity can restore it after compaction, but neither can
  force model attention.
- No `shell`/arbitrary-command check type -- see `DESIGN.md` section 2 and `SECURITY.md` for why that
  would have been a durable RCE primitive plantable via prompt injection.
- No same-directory HMAC/signing scheme for cross-session forgery -- `THREAT_MODEL.md` section 4
  explains why that would be security theater, not a real fix, in a single-user trust domain.
- No cross-session or cross-provider sharing -- each session's pins are its own; see the comparison
  table above and `DESIGN.md`'s usage-doctrine addendum for why that boundary is deliberate, not a gap.

## Packaging checklist (for a future standalone extraction)

**Already true, verified 2026-07-30:** every path in the shipped code resolves relative to `__file__`,
`sys.executable`, or the invoking session's own cwd -- never a hardcoded machine, user, or workspace
path (`grep -rn "D:\\\\!! CLAUDE\|Yogi\|Yogev" pins.py install.py hooks/` -- zero matches; note this
README, `DESIGN.md`, and `BRIEF.md` themselves still carry workspace-internal references and are not
yet scrubbed for publication -- see "still open" below).

**Standalone-portability gap closed 2026-07-30:** checkable facts (`git_branch`, `path_exists`, etc.)
resolve against the INVOKING session's actual project, threaded through as an explicit `repo_root`
parameter rather than a module-level constant. One clone of this tool works pointed at any project.

**Settled 2026-08-10, after an 8-model SOTA-evolution consult (6 responded) --
`reviews/sota-evolution/SYNTHESIS.md` has the full record:**

- **License.** Current recommendation: **Apache-2.0**. The original selection was arbitrary, so it
  was reopened in the 2026-08-15 three-product review. Grok 4.5, DeepSeek V4 Pro, and Sonnet 5 all
  recommended keeping Apache for the open cores because it supports genuine OSS adoption and an
  explicit patent grant. Commercial value should live in new governance, hosting, integration, and
  support products—not restrictions retrofitted onto the local core. See `LICENSE` here and the
  portfolio strategy at `knowledge/products/agent-runtime-trio/strategy.md` in the parent workspace.
- **`SECURITY.md` and `THREAT_MODEL.md`** now exist, extracted from `DESIGN.md` section 8 -- three
  independent reviewers called the existing security honesty a selling point for publication, not a
  liability.
- **Name.** "Flashback" stays the display name (near-unanimous). The bare package name is taken
  everywhere that matters -- PyPI, npm, and as a dormant GitHub org/heavily-reused repo name (see
  `reviews/sota-evolution/name_availability.md`). Five compound candidates
  (`flashback-context`, `flashback-pins`, `claude-flashback`, `agent-flashback`,
  `flashback-compaction`) are confirmed available on all three surfaces as of 2026-08-10. Final choice
  among them is not decided yet.

**Still open, deliberately left as human decisions rather than made silently here:**

- **Packaging mechanism.** `install.py` mutating `.claude/settings.local.json` was flagged by every
  reviewer as unfit for public distribution. A Claude Code plugin manifest and/or a PyPI console
  script are the recommended replacements (`SYNTHESIS.md` items B28-B29) -- not built yet.
- **Publish trigger.** Whether/when to actually extract and publish is not settled -- opinions among
  the consult ranged from "ship it" to "this needs a P0 redesign pass first" (`SYNTHESIS.md` section
  D6/B2). Everything above is preparation, not a recommendation to publish now.
- **Sanitization pass and full git-history scan.** This README and `DESIGN.md` are the two files
  actually staged for eventual public release; `BRIEF.md` and everything under `reviews/` are internal
  research/historical artifacts, and whether they ship at all (versus staying workspace-internal) is a
  packaging-scope decision, not merely a find-and-replace (`SYNTHESIS.md` item A17).
- **Claude Code hook-schema compatibility.** `install.py` was built and verified against this
  workspace's own `.claude/settings.local.json` schema, which is Claude Code's actual current
  behavior here, not a documented/versioned public API (`SECURITY.md`, `THREAT_MODEL.md` section 2) --
  re-verify against whatever version a target environment runs before trusting the installer there
  unmodified.

## Further reading

- `DESIGN.md` -- full design, the original three-reviewer architecture pass, the four-reviewer
  security hardening pass, the usage-doctrine and self-compaction addenda.
- `CONTRIBUTING.md` -- safety expectations and the DCO-based contribution path.
- `BRIEF.md` -- the original mandate and framing this project started from.
- `SECURITY.md` / `THREAT_MODEL.md` -- what to trust, what not to, and what changes under a public
  release.
- `reviews/sota-evolution/` -- the 2026-08-10 consult: full brief, all 6 raw model reviews, the
  synthesis, and the two measurement/research artifacts (ensemble injection cost, name availability)
  it produced.
