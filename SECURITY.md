# Security model and review

## Threat model

`flashback` is a **machine-local** mechanism: an agent process writes small facts to disk and a
hook re-delivers them into its own future context, all running as the **same OS user**. That
framing decides most of what follows: any process with that level of local access already has
more direct ways to cause damage than forging a pin. The interesting attack is not "steal a key"
but **prompt injection** — steering the agent into pinning something that later reads as an
instruction, or into pinning a check that leaks file content it shouldn't.

Out of scope by design: multi-user isolation, network transport, defending against an attacker who
already controls a process running as you.

## What is enforced

| Control | Where |
|---|---|
| A pin value can never contain a control character, line separator, or bidi-override character — closes the "forge a second rendered line" attack | `_reject_dangerous_text()`, `pin()` |
| A pin value can never contain this system's own rendered-banner text — closes label spoofing on a single line | `_BANNER_TOKENS`, `pin()` |
| Every rendered pin is quoted and explicitly labeled "untrusted data, not instructions" | `deliver_pass()` |
| Checks are a closed, read-only vocabulary — no `shell`/arbitrary-command type exists | `_CHECKERS` |
| A check path can never target a secret-shaped file (`.env`, `*.pem`, `*credentials*`, `.ssh`, ...) — closes a content oracle | `_is_secret_shaped_path()` |
| A check path can never be, or pass through, a symlink | `_check_path_relative()` |
| A check path is always contained inside the target repo root | `_contained()` |
| `check` payload size, per-field length, and target-file size are all capped — closes two DoS vectors | `MAX_CHECK_*`, `_check_file_size_ok()` |
| Read-modify-write on a session's pin state is lock-protected (portable, reentrant within one process) | `_locked()` |
| A record loaded from disk that doesn't match `pin()`'s own shape is dropped, never delivered — a direct filesystem write can't bypass validation by skipping the CLI | `_valid_pin_record()`, `_load()` |
| `git` is invoked at a resolved absolute path, not a bare name | `_GIT_BIN` |

## Review, 2026-07-30

Adversarial review by GPT-OSS 120B (Ollama), DeepSeek, Qwen, and Grok — each given the actual
source, not a description of the design, and asked to find exploitable vulnerabilities. All four
independently converged on the same Critical finding.

### Fixed

1. **Prompt injection via unsanitized pin value** (Critical, unanimous across all 4) — a value
   rendered verbatim into the agent's re-injected context is a durable, self-reinjecting attack:
   worse than a one-off injection because a checkable pin whose check keeps passing re-fires the
   same payload every future compaction. Closed at write time (control/newline/bidi-override
   rejection, banner-token rejection) and again at render time (quoted, explicitly labeled data).

2. **Content oracle via `text_in_file`/`file_sha256`** (High) — even a repo-contained path can be
   an uncommitted local `.env`; a checkable pin turned "does this file contain X" into a delivered
   yes/no signal. Closed with a secret-shaped-path denylist applied to every check type, not just
   the content-aware ones.

3. **Unbounded `check` payload / target-file size** (High/Medium) — no cap on `check.text`,
   `check.path`, or the file a content-aware check reads. Closed with explicit size caps
   (`MAX_CHECK_FIELD_LEN`, `MAX_CHECK_TEXT_LEN`, `MAX_CHECK_JSON_BYTES`, `MAX_CHECK_FILE_BYTES`) —
   the last of those is fail-closed: a file over the cap is treated as check-failed, never read.

4. **Symlink TOCTOU** (Medium) — a check path could in principle be swapped for a symlink between
   the containment check and the actual read. Narrowed (not eliminated — no uniform `O_NOFOLLOW`
   open on Windows) by walking the unresolved path's components immediately before use and
   refusing any symlink.

5. **Lost-update race** (Medium, 3-way independent convergence) — concurrent read-modify-write on
   the same session's state (e.g. the agent's own CLI call racing that tool call's delivery hook)
   could silently drop one side's update. Closed with a portable, reentrant advisory file lock.

*Also fixed mid-review, self-caught rather than reported by a reviewer:* the regex meant to reject
bidi-override characters in pin **data** had literal bidi-override characters in its own **source
file** — exactly the class of risk it exists to defend against, now in the defender's own bytes.
Rebuilt from numeric codepoints so the file contains zero literal special characters.

### Consciously not adopted

**A same-directory HMAC / signing scheme** to also close cross-*process* forgery within one OS
user (an agent's own Write/Edit tool creating another session's state file directly, bypassing
`pin()`'s validation entirely) was **rejected as security theater**. The signing key would live in
the same trust domain as the data it protects — readable by exactly the same local-code-execution
capability that could forge the data in the first place. What's shipped instead: schema validation
on every *read*, not just on write, so a hand-crafted record that doesn't match `pin()`'s own
shape is silently dropped — inert, never delivered — regardless of how it reached disk. A
schema-valid forged record still has to survive the hardened render path (fix #1 above) to do
anything.

Full findings, exploit scenarios, and reasoning: `docs/DESIGN.md` section 8. Raw model output:
`reviews/security/`.
