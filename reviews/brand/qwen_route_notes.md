# Qwen brand consultation -- the actual route that worked

Attempted 2026-07-30, five ways across two providers before landing on a third. Recorded in full
because the failure modes are real and will recur on other demanding prompts to this model family
-- see `~/.claude/projects/D-----CLAUDE/memory/reference_nous_qwen_524_openrouter_fallback.md`.

1. `nous/qwen/qwen3.6-plus` via Nous's own endpoint -- failed twice, `HTTP 524`. Confirmed cause:
   Nous's API is fronted by Cloudflare; the dispatch is non-streamed, so a sufficiently long
   generation can exceed Cloudflare's edge timeout before the origin finishes responding. Not a
   content or prompt problem -- an infrastructure one.
2-3. `qwen/qwen3.6-35b-a3b` via OpenRouter (genuinely different origin, not a retry of #1) --
   fixed the timeout entirely, but returned EMPTY output text at three escalating `--max-tokens`
   budgets (8000 default, 16000, 32000), each hit exactly, `reasoning_tokens` scaling roughly
   proportionally (6050 / 11185 / 22223).
4. Same OpenRouter model at 100000 -- a real order-of-magnitude jump, not another doubling, per
   Yogev's explicit direction not to give up on the doubling pattern. **Ran to full completion
   (exit 0, not killed, not timed out), cost $0.16 real money, consumed the entire 100000-token
   cap (73376 of it on reasoning), and STILL produced zero output text.** This is the fourth data
   point at the fourth budget size, all with the identical signature -- confirmed, not assumed,
   that this specific OpenRouter deployment of qwen3.6-35b-a3b does not converge on this prompt
   shape at any tested budget. (An earlier note here guessed the 100k attempt looked "killed by a
   client-side timeout, not a provider problem" before this result came back -- that guess was
   WRONG. Corrected once the real evidence landed, not left standing because it sounded tidier.)
5. **`qwen3.5:cloud` via Ollama Cloud (`ollama-cloud` provider, a THIRD distinct infrastructure
   path) -- SUCCEEDED.** A first attempt at 100000 hit a hard, informative wall: `HTTP 400:
   max_tokens (100000) exceeds model's maximum output tokens (65536) for model qwen3.5:cloud`.
   That error told us the model's real ceiling. Retried at exactly 65536 and got a complete,
   well-structured response (17530 output tokens used, comfortably under the cap) -- full text in
   `qwen_brand.md`.

**The lesson, not just the anecdote:** two DIFFERENT infrastructure limits (Cloudflare's edge
timeout on a non-streamed call; genuine non-convergent reasoning on a specific
provider+model+prompt combination that no amount of tested budget fixed) look identical from the
outside -- "the request failed" -- but need different fixes, and neither one is "try the same
thing again." Stopping after the first plausible-looking dead end (or the second, or the third)
would have been premature; the model family was reachable and had something real to say the whole
time, on a fourth genuinely different path.

**Qwen's own top pick: `receipt`.** Independently listed by Grok too (as one of its 8 candidates,
not its top pick) -- the only name candidate any two of the three models converged on. Pairs with
`gossip` on a rumor/proof axis ("gossip is rumor, receipts are proof" -- Qwen's own framing).
