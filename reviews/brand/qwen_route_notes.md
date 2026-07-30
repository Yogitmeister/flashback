# Qwen brand consultation -- the actual route that worked

Attempted 2026-07-30, four ways. The first three failed with two DIFFERENT, now-diagnosed root
causes; the fourth succeeded. Recorded in full because both root causes are real and will recur
on other demanding prompts to this model family -- see
`~/.claude/projects/D-----CLAUDE/memory/reference_nous_qwen_524_openrouter_fallback.md`.

1. `nous/qwen/qwen3.6-plus` via Nous's own endpoint -- failed twice, `HTTP 524`. Confirmed cause:
   Nous's API is fronted by Cloudflare; the dispatch is non-streamed, so a sufficiently long
   generation can exceed Cloudflare's edge timeout before the origin finishes responding. Not a
   content or prompt problem -- an infrastructure one.
2. `qwen/qwen3.6-35b-a3b` via OpenRouter (genuinely different origin, not a retry) -- fixed the
   timeout entirely, but returned EMPTY output text at three escalating `--max-tokens` budgets
   (8000 default, 16000, 32000), each hit exactly, with `reasoning_tokens` scaling roughly
   proportionally (6050 / 11185 / 22223). Non-convergent reasoning for this model + this specific
   long, multi-part-criteria prompt at those budget sizes, not simple under-provisioning.
3. Same OpenRouter model at 100000 -- attempted after diagnosis suggested "maybe just needs a lot
   more room, not a fundamentally broken response," per Yogev's explicit direction not to give up
   after the doubling pattern. (Result not yet known if this note predates that run finishing.)
4. **`qwen3.5:cloud` via Ollama Cloud (`ollama-cloud` provider) -- SUCCEEDED.** A first attempt at
   100000 hit a hard, informative wall: `HTTP 400: max_tokens (100000) exceeds model's maximum
   output tokens (65536) for model qwen3.5:cloud`. That error told us the model's real ceiling.
   Retried at exactly 65536 and got a complete, well-structured response (17530 output tokens
   used, comfortably under the cap this time) -- full text in `qwen_brand.md`.

**The lesson, not just the anecdote:** two DIFFERENT infrastructure limits (Cloudflare's edge
timeout on a non-streamed call; a per-model max-output-token ceiling) look identical from the
outside -- "the request failed" -- but need different fixes (change provider; raise the budget to
the model's *actual* ceiling, discoverable from the error message itself, not guessed at by
doubling). Stopping after either failure alone would have been premature; the model was reachable
and had something real to say the whole time.

**Qwen's own top pick: `receipt`.** Independently listed by Grok too (as one of its 8 candidates,
not its top pick) -- the only name candidate any two of the three models converged on. Pairs with
`gossip` on a rumor/proof axis ("gossip is rumor, receipts are proof" -- Qwen's own framing).
