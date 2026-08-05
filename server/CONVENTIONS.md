# Conventions: operations that mutate a real child's data

A checklist, not a framework. `grant_pilot_consent()` and
`register_pilot_learner()` (`foundation/identity.py`) already do this —
they weren't written against this checklist, this checklist was written
*from* them, after the consent-reorder fix. Apply it going forward to any
new function that creates, changes, or removes something tied to a real
learner — not to internal helpers, reads, or reference-data writes (e.g.
seeding `meaning_graph` content has no learner behind it and doesn't need
this).

This is the same shape ParthOS's architecture calls an **Action**
(`ParthOS/ARCHITECTURE.md` §3) — named, versioned, pre/post-conditioned,
audited. Nothing here requires ParthOS to exist; it's the pattern made
concrete inside Parth's own code, so the eventual extraction is a rename,
not a rewrite.

## The checklist

1. **State the precondition in the docstring, not just the code.** What
   has to already be true for this call to be valid? `grant_pilot_consent`
   states it plainly: the child identity must already exist — call
   `register_pilot_learner` first. If the precondition isn't checked in
   code (not just documented), that's a bug, not a convention violation to
   fix later.
2. **One operation, one responsibility — split rather than overload.**
   `register_pilot_learner` creates identity/profile only.
   `grant_pilot_consent` grants consent only. Before the fix, one function
   did both as an unstated side effect; splitting them is what made the
   ordering bug fixable at all. If a new operation feels like it's "also"
   doing a second unrelated thing, that's the signal to split it before
   writing more code, not after.
3. **State the effect and postcondition in the docstring.** What changes,
   and what must hold true after it commits? Not exhaustive prose — one or
   two sentences a reviewer can check the code against.
4. **Idempotent wherever the operation allows it.** Prefer
   `INSERT ... ON CONFLICT DO UPDATE` / `DO NOTHING` over "assume this is
   the first call." Both `register_pilot_learner` and `grant_pilot_consent`
   are safe to call again; callers shouldn't have to track whether they
   already ran.
5. **One log line recording who and why.** Not a full audit trail —
   `log.info("pilot_consent_granted", learner_id=...)` is the bar. Enough
   that "who did this, and under what call, at what time" is answerable
   from logs alone.
6. **If the operation reads as consent-gated, gate it before the write,
   not after.** The exact bug this checklist generalizes from: consent was
   collectible only as a side effect of registration, called *after* the
   thing it was supposed to gate had already run. `check_consent()` /
   `is_child_without_consent()` exist in the same file — use them, don't
   re-derive consent logic per call site.

## What this is not

Not a base class, a decorator, or a required interface — none of that
until there's enough real usage to know what a shared abstraction would
actually need to do (see `ParthOS/docs/DESIGN_BASIS.md` §5.1's autopoiesis
framing: let the system's own operation produce the specification). Right
now this is a checklist a reviewer can hold a diff up against, nothing
more.
