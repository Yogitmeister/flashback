# Flashback — pristine/disposable context partitioning

**Status:** new project, 2026-07-30. Spun out of the `gossip` session-bus work, where it was
correctly judged out of scope (gossip is a messaging tool; this is context management).

**Name:** settled as "Flashback" (2026-07-31), over "Al's Hammer" and the original "Alzheimer"
working title — a disease name on a public memory tool invites criticism that has nothing to do
with the engineering. The two kinds below (PRISTINE/DISPOSABLE in this brief's original framing,
`checkable`/`uncheckable` in the settled design) are now also named for humans to say out loud:
**Anchor** and **Flicker** — see `DESIGN.md` section 9.

---

## The idea, in Yogev's framing

Partition a session's context into two kinds:

- **PRISTINE** — enduring, task-specific state that must **not** degrade. Decisions, contracts,
  constraints, the next action.
- **DISPOSABLE** — everything else, freely compressible and lossy.

Compaction wrecks both indiscriminately today. The proposal: keep the pristine partition somewhere
compaction cannot reach, let the disposable part be summarised, and restore the pristine part
verbatim afterwards.

## Why this version is implementable when the original was not

The naive reading — "partition the context window" — is impossible. You cannot carve a
transformer's window or direct its attention; there is no API for "this region is protected".
Yogev reports the idea was shot down before, and heard that way it deserved to be.

This version moves the pristine partition **out of the window onto disk** and re-injects it at the
compaction boundary. That needs no harness cooperation, no model change, and no vendor buy-in.
Same idea, implementable framing. **The reframe is the whole unlock.**

## Why it matters more as sessions get longer

Lossy summarisation **compounds**: after N compactions the disposable partition is a summary of a
summary of a summary, and detail loss grows superlinearly in N. A disk-backed pin is re-read
verbatim each time, so its fidelity is **flat in N**.

The gap therefore **widens with every compaction**. This is not a convenience feature; it is the
property long-horizon agent work actually needs.

## The mechanism, verified

`PreCompact` is the hook, and it gives two independent levers:

1. **Persistence** — the hook writes state to disk *before* compaction. Files are outside the
   context window, so compaction cannot touch them. Delivery hooks re-inject after.
2. **Steering** — the PreCompact dispatcher collects each hook's **raw stdout** and passes the
   joined text to the summariser as `customInstructions`. Verified in the 2.1.220 binary:
   `results.filter(succeeded && !blocked && output.length > 0).map(output.trim())`. So a session
   can author what survives, even though it cannot trigger compaction.

**Boundary:** a session cannot trigger its own `/compact` in the CLI. A queued item is a slash
command only if it starts with `/` **and** is not flagged `skipSlashCommands`, and every
programmatic injection path sets that flag. Expansion survives on the interactive keyboard, the CLI
entry point (`claude -p "/compact"` executes — verified), and the Agent SDK, where an embedding
host decides. So: **the human owns the trigger, the session owns the content.**

## Prior art in this workspace

`_pending/flashback_pin_extract.py` — a working implementation, extracted intact rather than
rewritten. Verified before extraction:

- keyed upsert — re-pinning a key **replaces** it, so state cannot accumulate contradictory copies
- hard byte budget (6000) with **reported** eviction, never silent truncation
- oversized values **refused**, not truncated
- age stamping on every entry
- survives the PreCompact → post-compaction round trip verbatim

Also reusable: `tools/session_bus/bus.py` (the delivery mechanism, and the self-state-vs-peer
framing distinction) and `.claude/hooks/session_continuity.py` (a working PreCompact hook).

## The four unsolved problems — this is the actual work

1. **Staleness beats loss.** A stale pin preserves **confident wrongness**, and will be trusted
   over fresh evidence *because* it reads as canonical. A lossy summary degrades toward vagueness,
   which invites re-checking — it fails safe. Persistence without invalidation makes the failure
   mode **worse**. Age stamping is a hint, not a solution. Needs real invalidation, cheap
   re-verification, or confidence decay.
2. **Curation is unsolved.** Deciding *what* is load-bearing is the hard part. An automatic
   heuristic (last message + recent tools) is a guess, not a partition. Who decides, and when?
3. **It competes for the resource it protects.** Re-injected state occupies the headroom compaction
   just reclaimed. Unbounded, it grows until it alone triggers compaction — a loop that reclaims
   nothing. The budget bounds the damage; it does not solve allocation.
4. **Mid-window degradation is untouched.** Long sessions also degrade from attention dilution
   inside a single window. This helps only across boundaries. Be explicit that it is half the
   problem.

Also settle: **what is the genuine delta** over `CLAUDE.md`, memory files, and task lists, which are
already durable curated state? The narrow answer so far: automatic re-injection of **session-scoped,
task-specific** state at the compaction boundary, where those surfaces are global and
hand-maintained. Pressure-test whether that delta justifies a project.

## Mandate

Mature this from a working prototype into a real design. Pressure-test hard, then build.
Consult **DeepSeek, Qwen, and Grok** for independent architectural review — especially on problem 1
(staleness/invalidation), which is the one most likely to make the cure worse than the disease.
Dispatch them directly on their own budgets:

```bash
python tools/agents/models/deepseek/dispatch.py --role "..." --task "..." --output "..."
python tools/agents/models/nous/qwen.py           --role "..." --task "..." --output "..."
python tools/agents/models/xai/grok.py            --role "..." --task "..." --output "..."
```

Back-burner priority: `gossip` is the active foreground project. Do not touch
`tools/session_bus/`, `.claude/hooks/session_bus_drain.py`, or
`.claude/hooks/session_continuity.py` — another session owns those. Read them freely; copy what you
need into this project.
