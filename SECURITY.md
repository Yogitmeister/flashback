# Security Policy

**Status:** drafted 2026-08-10 from `DESIGN.md` section 8 (the 2026-07-30 security hardening pass)
and `reviews/sota-evolution/SYNTHESIS.md` item C3.3. Cross-checked directly against the current
`pins.py` and `install.py` source, not just the design description.

## Flashback is a fidelity mechanism, not a security boundary

Flashback re-injects context an agent explicitly chose to keep, and mechanically re-verifies the
checkable half of that context against live state every time it is delivered. That is what it is
for: making sure a fact that survives a context compaction is either still true or is loudly flagged
as no longer confirmed. It is **not** a sandbox, not an authorization system, not a cross-session
lock, and not a secret store, and it should not be relied on as any of those things. `THREAT_MODEL.md`
has the full picture; this file is the disclosure policy and the plain-language summary of what to
trust and what not to.

## Reporting a vulnerability

Flashback currently lives inside a private, single-user workspace repository and has not yet been
extracted to its own public repository or tagged release (`reviews/sota-evolution/SYNTHESIS.md` item
C3.2). Until that extraction happens there is no public disclosure address or issue tracker to point
to, and **this section is a placeholder** that must be filled in with a real contact -- a maintainer
email, or the target repository's GitHub Security Advisories flow -- before any public release. Its
absence here is an open release-blocking gap, not a claim that no way to report a problem exists.

## Supported versions

There is no tagged release or version scheme yet -- no `pyproject.toml`, no `CHANGELOG.md`, no
`__version__`. This document describes the security posture of the source as of the 2026-07-30
hardening pass and applies to the current state of the code, not to a specific pinned version. A
versioned support policy is a packaging prerequisite (`reviews/sota-evolution/SYNTHESIS.md` item
C3.2) that has not been built yet.

## What to trust, plainly stated

Four independent adversarial security reviewers (GPT-OSS 120B, DeepSeek, Qwen, and Grok) reviewed
the actual source of `pins.py` and its two hooks on 2026-07-30; the full findings and disposition are
in `DESIGN.md` section 8. The list below states plainly what that pass, and the source as it stands
today, actually support -- adapted from an independent reviewer's (Sol's) disclosure checklist:

- **Hooks execute automatically once installed.** `install.py` registers `PreCompact`,
  `SessionStart`, and `PostToolUse` hooks in Claude Code's own hook configuration. Once that
  registration exists, Claude Code itself invokes them on those lifecycle events with no further
  per-use confirmation from anyone.
- **State is plaintext local data.** Pins and delivery metadata are written as plain JSON under the
  local Claude config directory (`~/.claude/flashback/pins/` by default, or `$CLAUDE_CONFIG_DIR` if
  set). There is no encryption today, and none is implied anywhere in the design. If an optional
  encryption design is added later, this line should be updated to say so explicitly rather than
  assumed.
- **Same-user processes can forge records.** Anything else running as the same OS user -- including
  an agent session steered by prompt injection into misusing its own file-write tools -- can write or
  edit a pin's on-disk JSON directly. Schema validation on every read (right types, no control
  characters, no forged banner text, size limits respected) makes a record that does not match what
  the code's own writer would have produced inert -- silently dropped, never delivered -- but this
  does not authenticate *who* wrote a well-formed record; it cannot. There is no cryptographic
  signing, and a same-directory signing key would sit in the same trust domain as the data it claims
  to protect (see `THREAT_MODEL.md`'s residual-risk section for why that would be security theater,
  not a real fix, under the current deployment model).
- **Re-injected annotations are prompt-level data, not a structural isolation boundary.** Every
  delivered line is explicitly labeled "untrusted data, not instructions" and quoted, and the
  characters that could forge a second banner line or a fake instruction boundary are rejected at
  write time. That is a real, structural reduction in attack surface. It is still, ultimately, a
  convention inside the model's own context window, not an enforced technical isolation the model
  cannot be talked out of -- a single-line value that reads as a plausible instruction without using
  any rejected character remains a risk the data layer alone cannot close.
- **No arbitrary shell checker exists.** The set of check types a pin can carry is a closed enum --
  `path_exists`, `path_absent`, `text_in_file`, `file_sha256`, `git_branch`, `git_head_prefix` -- and
  none of them accept or execute a caller-supplied command string. A `shell`-type check was
  considered during design and deliberately not built, because an automatically re-firing,
  agent-writable, unattended shell check would be a durable remote-code-execution primitive that
  prompt injection could plant (`DESIGN.md` section 2).
- **Checks are repository-contained, with documented symlink/TOCTOU limitations.** Every
  path-bearing check is confirmed to resolve inside the repository root before use, and a symlink at
  any component of the literal path is refused immediately before the read. That narrows the window
  for a swap-the-target race to "between this check and the caller's next line"; it does not
  eliminate it. A full fix needs an OS-level no-follow open, which is not uniformly available on
  Windows.
- **Flashback is not a sandbox, an authorization system, a cross-session lock, or a secret store.**
  It does not execute arbitrary code and does not grant or check permissions for any action. Its
  internal write lock protects one session's own state file against a concurrent read-modify-write
  race with itself; it does not coordinate or arbitrate between sessions. Every check path is refused
  outright, for every check type including plain existence, if it matches a secret-shaped pattern
  (`.env`, `*.pem`, `*.key`, `id_rsa*`, `*credentials*`, and similar), so it should never be pointed
  at, or used to hold, secret material.
- **Fail-open behavior preserves Claude's availability but can lose restoration unless surfaced.**
  The internal write lock waits briefly for a same-session conflicting writer, then proceeds without
  the lock rather than risk wedging a hook indefinitely. That keeps Claude Code responsive, but in
  that narrow window a concurrent write can be silently lost -- which means a pin that should have
  been saved, updated, or evicted may not be restored as expected at the next delivery. Nothing in
  the current source logs or otherwise surfaces when that has happened.
- **Uninstalling removes the hook registration, not the stored state.** `install.py --uninstall`
  removes only Flashback's own entries from Claude Code's local hook configuration. It does not
  delete previously written pin or delivery-metadata files; those remain on disk under the local
  Flashback state directory until removed by hand.
- **Some claims here are mechanically verified; others are annotations.** A `checkable` pin (an
  "Anchor") is re-run fresh, against live state, through one of the six check types above, every time
  it is delivered -- a real, repeatable, mechanical confirmation. An `uncheckable` pin (a "Flicker")
  is a judgment call -- a decision, an intent -- that nothing in the system can mechanically confirm;
  it is rendered once, then re-rendered as a loud "unverified claim" warning after surviving one
  compaction, then dropped. Treat the first kind as re-confirmed fact and the second kind, always, as
  exactly what its label says: a claim to re-derive or re-pin, not a verified one.

**Do not say prompt injection is "fixed."** The 2026-07-30 hardening pass measurably reduced the
structural attack surface -- an unsanitized pin value can no longer forge a banner line, spoof a
system message, or break out of the rendered block. It did not, and cannot from the data layer alone,
close the remaining semantic risk: a value that reads as a plausible instruction without using any
rejected character or token is still readable by a model as something to act on. That residual is
documented, not eliminated. The "untrusted data, not instructions" framing on every rendered line is
a strong prompt-level mitigation for it, not a structural guarantee.

## Recommended hardening for higher-risk deployments

The mitigations above were built and reviewed against a single-user personal workspace operating on
trusted repository content. `THREAT_MODEL.md` documents the delta once that assumption changes (an
untrusted repo, a shared machine, or CI) and recommends a **paranoid mode** for that case: a
configuration, not yet built, that would disable the two content-reading check types (`text_in_file`,
`file_sha256`) and permit only git-metadata checks (`git_branch`, `git_head_prefix`) and
non-content-reading path checks (`path_exists`, `path_absent`). This is a recommendation for future
work, not a shipped feature -- no such mode exists in the code today.

## See also

- `THREAT_MODEL.md` -- the full threat model, including the public-release delta and the accepted
  residual risks in more detail.
- `DESIGN.md` section 8 -- the original security hardening pass this document is drawn from,
  including the full findings table and the reasoning behind each accepted residual risk.
