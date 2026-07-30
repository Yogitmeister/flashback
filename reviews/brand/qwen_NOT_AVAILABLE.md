# Qwen brand consultation -- not obtained

Attempted 2026-07-30, three ways, all unsuccessful:

1. `nous/qwen/qwen3.6-plus` via Nous's own endpoint -- failed twice with `HTTP 524` (Cloudflare
   edge timeout on a non-streamed, reasoning-heavy completion). See
   `~/.claude/projects/D-----CLAUDE/memory/reference_nous_qwen_524_openrouter_fallback.md`.
2. `qwen/qwen3.6-35b-a3b` via OpenRouter (a genuinely different route, not a retry of #1) --
   fixed the timeout, but returned **empty output text** at three escalating `--max-tokens`
   budgets (default, 16000, 32000), each hitting its cap exactly with `reasoning_tokens` scaling
   roughly proportionally (6050 / 11185 / 22223) and never reaching the actual answer. This is
   the documented "thinking token cap" pattern (see the same memory file above), except raising
   the budget didn't fix it here -- evidence of non-convergent reasoning for this specific model
   on this specific long, multi-part-criteria prompt, not simple under-provisioning.

Stopped after the third attempt rather than continuing to raise the budget (escalating real
provider cost -- ~$0.008 / $0.02 / $0.04 -- for zero usable output each time). DeepSeek and
Grok's independent consultations (`deepseek_brand.md`, `grok_brand.md`) are complete and were
used for the synthesis in PRESS-RELEASE.md / LINKEDIN-POST.md's reviewer notes. 2 of 3 planned
independent brand opinions, honestly short one, not silently presented as three.
