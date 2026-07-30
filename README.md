<p align="center">
  <img src="https://img.shields.io/badge/status-work%20in%20progress-yellow" alt="work in progress">
  <img src="https://img.shields.io/badge/python-3.9%2B-blue" alt="python 3.9+">
  <img src="https://img.shields.io/badge/dependencies-none-brightgreen" alt="zero dependencies">
  <img src="https://img.shields.io/badge/license-PolyForm%20Noncommercial%20(draft)-orange" alt="license draft">
</p>

<h1 align="center">alzheimer <sub><sup>(working title, not final)</sup></sub></h1>

<p align="center">
  <strong>Facts an AI coding agent pins to disk so they survive context compaction,<br>
  re-verified on delivery instead of just trusted.</strong>
</p>

---

> **This repo is a work in progress and not yet public-facing.** Code, tests, and the security
> review are real and passing; the name, the license, the README's own polish, and a real
> standalone-install story are not finalized. See "Status" below before assuming anything here is
> a finished product.

## The idea

Claude Code (and similar agent harnesses) periodically **compact** a long session: the older
conversation gets summarized to free up context space. That summary is lossy by nature — it's a
generic pass over the whole transcript, and it doesn't know which handful of facts you actually
need to survive verbatim.

`alzheimer` lets the agent **pin** those facts to disk before that happens, and re-injects them
automatically afterward:

- **`checkable`** pins carry a small, closed-vocabulary mechanical check (a git branch, a file
  existing, a file's hash) and are **re-verified fresh on every delivery** — never stale, because
  a checkable pin either still passes or evicts itself.
- **`uncheckable`** pins are judgment calls (a decision, a constraint, "the next action") that
  can't be mechanically verified, so they're deliberately short-lived: shown once, then flagged as
  an unverified claim after surviving one compaction unrefreshed, then dropped.

The split exists because a naive "just persist everything verbatim" version of this idea is
actively dangerous: a stale pin reads as *authoritative* and gets trusted over fresh contradicting
evidence, where a lossy summary at least degrades toward vagueness and invites re-checking. Four
independent AI models adversarially reviewed this design and its implementation before anything
here was called done — see `docs/DESIGN.md` and `reviews/`.

## Two levers, one boundary

An agent session cannot trigger its own compaction — that's the human's call, and this project
doesn't try to move that boundary. What it *can* do, and what this project is built entirely
around, is control **what survives** compaction and **what comes back afterward**, via two Claude
Code hook events:

- `PreCompact` — fires just before compaction. Persists state to disk (outside the context window,
  so compaction can't touch it) and can steer the summarizer.
- `SessionStart` / `PostToolUse` — fires when the session resumes. Re-injects the pinned state.

## Status

**Working, tested, security-reviewed, running in the originating workspace.** Not yet a
drop-in tool for an arbitrary project:

- [ ] **Name.** "alzheimer" is a working title. A disease name on a public tool invites criticism
  unrelated to the engineering — needs one deliberate decision before this goes public.
- [ ] **License.** Leaning [PolyForm Noncommercial 1.0.0](LICENSE) (same as this author's other
  public tool, `gossip`), not finalized.
- [ ] **Standalone repo-root resolution.** `pins.py`'s checkable-fact vocabulary (`git_branch`,
  `path_exists`, etc.) currently resolves the target project's root from where `pins.py` itself is
  installed, which only works when it's vendored inside the exact project it's protecting (true
  today in the originating workspace). Cloning this repo standalone and pointing it at a
  *different* project needs the root resolved from the invoking session's actual working directory
  (available in every hook payload as `cwd`) instead — not yet done.
- [ ] **Polish.** No logo, no worked walkthrough, no comparison to what else exists in this space.

## Install (current state — see the limitation above)

```bash
git clone https://github.com/Yogitmeister/alzheimer
cd alzheimer
python -m pytest tests/ -q                 # 74 pass, 1 skipped (symlink test needs elevation)
```

Registering the hooks: `install.py` was written for — and only tested against — the case where
this code lives *inside* the repo it's protecting (a `My Projects/alzheimer/` style subfolder).
It writes to that repo's own `.claude/settings.local.json`, matching Claude Code's own hook-config
schema, and never touches the git-tracked `.claude/settings.json`. Until the repo-root fix above
lands, treat cross-repo use as unverified.

## CLI

```bash
python pins.py pin --key branch --kind checkable \
    --value "on main" --check-type git_branch --check-arg expect=main

python pins.py pin --key decision --kind uncheckable \
    --value "use SQLite, not Postgres, for the local cache"

python pins.py pins
python pins.py unpin --key decision
```

Checkable pins require `--check-type` from a closed set — never an arbitrary command:
`path_exists`, `path_absent`, `text_in_file`, `file_sha256`, `git_branch`, `git_head_prefix`.

## Security

`docs/DESIGN.md` section 8 has the full write-up: four independent adversarial reviewers (GPT-OSS
120B, DeepSeek, Qwen, Grok) found the same Critical issue on the first pass — an unsanitized pin
value rendered into the agent's context is a durable, self-reinjecting prompt-injection vector —
and it's fixed, with 33 regression tests. Raw reviews in `reviews/`.

**Threat model, stated plainly:** this is a machine-local mechanism between an agent process and
its own future context, running as one OS user. Anything with that level of local access can
already do more damage more directly than forging a pin. The design's job is narrower: make sure
the *mechanism itself* — pin persistence and re-delivery — is not a way to smuggle in a new
instruction disguised as your own earlier data, and not a filesystem-content oracle. Both are
closed; a same-directory signing scheme to also close cross-process forgery within that one OS
user was deliberately **not** added (would be security theater — the key would sit in the same
trust domain as the data it protects).

## License

Currently ships [PolyForm Noncommercial 1.0.0](LICENSE) as a placeholder, matching this author's
other public repo — **not a final decision.** This repo is private; nothing here is granted to
anyone yet.
