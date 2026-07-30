## Structured Architectural Review

### 1. STALENESS BEATS LOSS (Problem 1)

**Verdict: Net‑negative without a mechanical invalidation mechanism.**

Your own analysis is correct: a re‑injected pin reads as authoritative, so the model will trust it over fresh contradictory evidence in the transcript. Lossy summarization, by contrast, degrades toward vagueness and *invites* re‑verification. Naive persistence therefore makes the agent *more confidently wrong* than doing nothing. This is the opposite of what we need. The age‑stamp is cosmetic – it adds a hint, not a guard.

**Cheapest mechanical invalidation that flips the verdict to net‑positive:**

Add a **compaction count field** to each pin (incremented each time the pin survives a compaction). The harness tracks a **staleness threshold** (configurable, default = 2). When a pin’s count exceeds the threshold, the re‑injection mode changes:

- **Count ≤ threshold** → inject as authoritative statement (current behavior).  
- **Count > threshold** → inject as a *verification request*, e.g.:  
  `[STALE PIN (key: <k>, last value: <v>) – confirm or update before using]`.  

The agent (or a downstream tool) can then issue a `pin confirm <key>` action that resets the count to 0, effectively re‑authorizing the pin. This is cheap: one integer per pin, a conditional branch during re‑injection, and a small protocol extension (one new tool call). It uses the existing age‑stamp machinery trivially. The token cost is a few words per stale pin – negligible compared to the risk of confident error.

Without this, the feature is harmful. With it, the agent treats stale pins as hypotheses to be checked, which is strictly better than the lossy summary’s vague reminder.

---

### 2. CURATION IS UNSOLVED (Problem 2)

**Verdict: Manageable with explicit agent‑initiated tool calls.**

Do not attempt automatic heuristics (e.g., “last assistant message”) – they will always guess wrong and violate the pristine/disposable partition. The only reliable curatorium is the agent itself, because only it knows what is load‑bearing.

**Concrete proposal:**

- Expose two harness tools: `pin(key, value)` and `unpin(key)`.  
- Teach the agent in the initial system prompt to pin only **decisions, constraints, and the immediate next action** – and to unpin or re‑pin when those change.  
- The harness does **no inference** about what to pin.  

This is cheap to implement and avoids the risk of the agent pinning the wrong thing (the agent is responsible for its own mistakes). If the agent forgets to pin, it suffers the same loss it would without the feature – not a regression. The staleness mechanism (problem 1) protects against the agent failing to unpin obsolete information.

---

### 3. IT COMPETES FOR THE RESOURCE IT PROTECTS (Problem 3)

**Verdict: Real but solvable with a quota and a safety check.**

The potential compaction loop is dangerous. A naive implementation could re‑inject pins that push the session back over the compaction threshold, triggering another compaction that does nothing but reclaim the pins’ own space.

**Concrete proposal:**

- Set the total pin budget to **no more than 10%** of the compaction threshold (e.g., 6000 bytes of 64 KB → 10% is 6.4 KB; fine).  
- After re‑injection, if the context size *including pins* still exceeds the compaction threshold, **force‑evict the oldest pins** until the total is below the threshold.  
- Ensure the harness suppresses repeated compactions within a single turn (e.g., a cooldown flag).  

This breaks the loop. The 10% rule guarantees that even if all pins are “urgent,” they cannot dominate the window. Eviction is already implemented – we just add a post‑injection check.

---

### 4. IT DOES NOTHING FOR MID‑WINDOW DEGRADATION (Problem 4)

**Verdict: Not a problem. Accept that this is a narrow fix.**

“Lost in the middle” is a real weakness, but it is a different mechanism from compaction loss. This feature targets *compaction boundaries*, which are a predictable and periodic failure point. Fixing one class of degradation is worthwhile even if another remains unsolved. Mid‑window attention decay is best addressed by positional encoding improvements or re‑ranking strategies, not by pinning. Do not let perfect be the enemy of good.

---

### 5. DELTA OVER CLAUDE.md / MEMORY / TASK LIST

**Answer: Build it, but only with the staleness fix from (1) and the budget safety from (3).**

The existing surfaces (CLAUDE.md, memory files, task list) are:

- **Global** – not session‑scoped.  
- **Human‑maintained** – require the user or an explicit agent action to write to them.  
- **Not automatically re‑injected** at compaction boundaries – the harness does not read them on every compaction.  

The delta is real: **automatic, session‑specific, compaction‑boundary re‑injection** without manual re‑derivation. Teaching the agent to “write to a file before compaction” is fragile – the agent may forget, the file may grow stale, and the handler must be custom. A built‑in pin system with the invalidation fix is reliable and low‑overhead.

However, the value rests entirely on solving problem 1. Without it, the delta becomes negative (confident errors). With it, the feature is a clear improvement over the status quo.

---

### 6. ALTERNATIVE ARCHITECTURE

**If I were starting over, I would build “protected messages” instead of pins.**

**How it works:**

- The agent can tag any message with a `[PROTECTED]` marker (e.g., via a tool call `protect(message_id)`).  
- The compaction algorithm **skips** protected messages – they are never summarized and always retained verbatim.  
- The agent can also `unprotect(message_id)` to allow summarization.  

**Why this is better:**

1. **No staleness problem** – the original message stays in context and is naturally updated by subsequent messages. If the agent writes a new decision, the old protected message remains but the agent can see the contradiction and act accordingly. There is no separate copy to become authoritative over the transcript.  
2. **No curation complexity** – the agent decides which messages to protect; same as pinning, but the granularity is message‑level, easier to reason about.  
3. **No context‑competition loop** – protected messages are a fixed set of IDs, not an external store. Their size is the same as if they had not been summarized; the compaction threshold applies to the total context, so there is no double‑counting. The agent can only protect a limited number of messages (the entire window is bounded).  
4. **No file I/O** – simpler to implement and debug.  
5. **Mid‑window benefits** – because the protected message remains verbatim, its content is not diluted by positional decay from other messages (though it still suffers from attention decay, but that’s a model‑level issue).

**Trade‑off:** Summary quality may degrade if many messages are protected, but that is the agent’s choice. The pin approach allows arbitrary compression of the protected content (since pins are short key/value), whereas protected messages keep the full text. For typical use (one constraint, one next action), a protected message of ~1KB is fine.

**Verdict on alternative:** This is the architecture I would build. It sidesteps the staleness and budget problems entirely while solving the same core problem (preserve critical state across compactions). The pin system can be viewed as a compressed, less safe variant. If the budget and invalidation complexity are acceptable, proceed with pins. If not, switch to protected messages. Either is better than nothing – but **only with a staleness guard**.