# Contributing to Flashback

Flashback is an Apache-2.0 safe context-admission project. Contributions should preserve its three
separate concerns: relevance, truth freshness, and lifecycle timing.

## Before opening a change

- Do not infer durable Pins from retrieved text; Anchors and Flickers are agent-curated.
- Keep checks inside the closed vocabulary; no arbitrary shell execution.
- Preserve fail-open hook behavior so retrieval or continuity cannot wedge a session.
- Treat every stored value as untrusted data when it is re-injected.
- Label lifecycle-addressing work honestly until the schema and hooks are implemented and tested.

## Validate

```bash
python -m pytest "tests/" -q
```

Security-sensitive changes to storage, containment, locking, verification, rendering, or hook
delivery require an explicit threat-model review.

## Developer Certificate of Origin

Contributions use the [Developer Certificate of Origin 1.1](https://developercertificate.org/).
Sign each commit with:

```text
Signed-off-by: Your Name <your.email@example.com>
```

Use `git commit -s` to add the line automatically. By signing, you certify that you have the right
to submit the contribution under this repository's Apache-2.0 license.
