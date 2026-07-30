## 5–8 Candidate Names

### 1. **Assert**  
**Why it fits:** “Assert” is a developer-native word that maps directly to the mechanism. Checkable pins behave like runtime assertions: they must pass on every read or they fail loudly. Uncheckable pins are like temporary assumptions—they don’t get asserted, so they expire. The word is short, plain, and carries the exact discipline the tool enforces.  
**Risk:** A few testing libraries use “assert,” but no standalone CLI tool owns the name. The bigger risk is that developers might initially think it’s a testing framework—positioning and tagline need to push past that fast.

### 2. **Stake**  
**Why it fits:** Double meaning works hard. “Stake a claim” mirrors pinning a fact. “At stake” captures the danger of stale memory. Checkable pins are firmly staked (re-verified each time); uncheckable pins are temporary stakes that get pulled. The concept of “staking” a fact onto a session is intuitive.  
**Risk:** Heavy crypto connotations (“staking tokens”) now live in every developer’s head. Could be read as a blockchain–adjacent product, which it isn’t.

### 3. **Prove**  
**Why it fits:** A verb name, exactly like the sibling “gossip.” Short, sharp, and imperative: “prove pin add.” It immediately communicates verification. Checkable pins prove themselves on every delivery; uncheckable pins can’t, so they’re transient. The name asks the user to take an active role in truth-tracking.  
**Risk:** “Prove” is a generic, high-frequency word. SEO and discoverability will be rough. Also, it could be mistaken for a formal verification tool (like Coq) or a testing helper.

### 4. **Anchor**  
**Why it fits:** Anchors hold things in place, but they also drag if unverified. Cognitive anchoring bias—the tendency to over-trust the first piece of information—is exactly the failure mode this tool prevents. The name works on both the mechanical and the psychological levels.  
**Risk:** Heavily saturated: Docker Anchor, Anchor.fm, many URL shorteners. Trademark real-estate is crowded. Also, the “bias” angle is clever but not immediately obvious without a tagline.

### 5. **Checkpoint**  
**Why it fits:** Developers already understand checkpoints as savestates that can be reverted. The twist here is that the “check” part is continuous—the tool doesn’t just save once, it re-verifies on every injection. The word is familiar enough to lower the learning curve.  
**Risk:** “Checkpoint” is a well-known ML term (model checkpoints) and a standard concept in databases and game engines. The tool will blend into noise. Also, it implies a full-state save, which is misleading—this is a small set of pins, not a snapshot.

### 6. **Surety**  
**Why it fits:** Checkable pins provide surety—a guarantee backed by mechanical proof. Uncheckable pins are a lower form of assurance with an expiration date. The word is rare enough to be ownable but still readable. It feels confident and slightly old-fashioned, which contrasts nicely with the disposable “gossip” sibling.  
**Risk:** Niche vocabulary. “Surety” is a legal/financial term (surety bond) that might resonate with corporate buyers but confuse indie devs scanning Hacker News. Could read as stiff.

### 7. **Factcheck**  
**Why it fits:** Blunt and honest. The tool literally checks facts on every delivery. The split between checkable and uncheckable maps perfectly to “verified facts” vs. “unverified claims.” It’s a compound word that explains itself in five seconds.  
**Risk:** “Fact check” is a common phrase (often used in journalism/politics), which could bring unwanted baggage. Also, it’s two syllables plus “check” – a bit long for a CLI tool. Might feel more like a GitHub action than a standalone tool.

---

## Top Recommendation: **Assert**

**Defense:** “Assert” is the only name that encodes the core mechanism as a native developer action without metaphor. When a developer sees it, they already know the contract: if I assert something, it must be true right now, or the system stops and tells me. That’s exactly what checkable pins do. Uncheckable pins are the intentional counterpart—things you *don’t* assert, so they carry no guarantee and expire. The word is short, memorably typed, and sits naturally alongside “gossip” as a sibling (both single-word nouns that are also verbs). No other candidate cuts through the noise of “AI memory tools” with the same surgical precision.

**Tagline:** “Pins that prove themselves.”

**Positioning (one paragraph for a skeptical dev scrolling HN):**

> You know how Claude Code compacts your session and loses details? Pinning facts to survive that sounds obvious—until you realize a stale pin is worse than a vague summary, because the agent trusts it like gospel. This tool replaces naive persistence with a simple discipline: **checkable pins** are re-verified against real system state (git branch, file hash, anything scriptable) on every injection; if reality changed, the pin changes or dies. **Uncheckable pins**—decisions, next actions, constraints—get a short leash: shown once, flagged as unverified after one compaction, then dropped. No silent lies, no Alzheimer’s metaphors, just a strict contract between memory and truth. It’s not another “AI memory” tool. It’s the one that knows the difference between a fact and a guess.

**One brand-angle launch risk:** The name “Assert” could cause initial confusion with the built-in `assert` functions in every language (Python, Node.js, etc.). Developers might assume it’s a testing helper or a runtime assertion library rather than a context-persistence tool. The tagline and landing page must lead with the “pinning facts” use case, not the word “assert,” to avoid being categorized as a QA tool. A short show-don’t-tell example (e.g., “`assert pin add –check 'git branch –show-current'`”) will disambiguate instantly.