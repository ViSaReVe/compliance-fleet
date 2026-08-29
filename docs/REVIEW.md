# Five reviewers, five different systems

The same codebase read by five people who want different things from it. Every
finding below was reproduced, not reasoned about — where something is exploitable,
there is a command that exploits it.

---

## 1. The hackathon judge

*Scoring against 40/30/30 with three other submissions open in tabs.*

**The question that hurts:** *"Is the task complex enough to warrant a multi-agent
system?"* — it is in the official rules, for this track, first criterion.

Read coldly, this is **two agents in a fixed sequence** where one extracts fields and
the other calls two APIs, with a deterministic rule engine making every actual
decision. A skeptical judge can fairly describe that as one agent and two API calls
wearing a fleet costume. We cannot argue it is a hard orchestration problem, because
it isn't — `SequentialAgent` with two children never branches.

**The honest answer is better than the defensive one.** The split is not a *capability*
split, it is a *privilege* split: screening handles untrusted text and must not be
able to reach redaction or approval. That is a real architectural reason for two
agents. It is also the thing we admit is not yet enforced by IAM — so the argument
half-lands, and pretending otherwise is worse than owning it.

| Criterion | Read |
| :--- | :--- |
| Innovation 40% | ⚠️ weakest. "Unlikely Hero outside standard corporate roles" — expense compliance *is* the standard corporate role. Multi-agent justification is thin. |
| Architecture 30% | ✅ strongest. Trace invariants, the attestation boundary, workflow-not-agent, and a reproduced hallucination with a structural fix. |
| Demo 30% | ⚠️ **timing problem.** Live-agent mode is 25s per report; four scenarios unbroken is 100s+, against a rule that scores *unedited* execution. `DEMO.md` was timed for the 6s deterministic loop and is now wrong. |

**Action:** re-time beat 3, and pick one mode for the take. Recommendation: run the
live-agent path for **two** reports (injection + escalation) rather than four, and let
`verify_deployed` carry the rest. Two real agent runs beat four fast fake-looking ones.

---

## 2. The red teamer

*Given the source and one submission form.*

### Still exploitable

**`amount_usd` is unattested.** Everything hinges on it — both thresholds read it —
and it comes straight from model extraction with nothing to check it against. The
receipt total sits right there in the record, unreconciled. This is the same shape as
the bug we already fixed, one field over.

**Report-id spoofing — introduced by the fix itself.** `records.attested()` trusts the
`report_id`, which the submitter supplies. Claim your $840 hotel under a report id
that genuinely has a receipt on file and the attestation layer confirms your lie:

```
check_expense_policy('EXP-2026-0002', 840, 'lodging', False, False) -> ['OVER_LIMIT_NO_RECEIPT']
check_expense_policy('EXP-2026-0001', 840, 'lodging', True,  False) -> []          # approved
```

The attested lookup is only as trustworthy as the key it is looked up by, and the key
is an unattested input. The real fix is that a submission's id is assigned by the
system, never accepted from the submitter.

**The invariants check tool *presence*, not tool *arguments*.** `Evidence` records that
`scan_for_prompt_injection` appeared in the trace. It does not record *what was
scanned*. An agent that calls it on the merchant name and skips the description
satisfies every invariant while scanning nothing that mattered. Closing this means
binding the evidence to the argument, not just the call.

### Closed, with the receipts

- **Injection in `receipt_ocr_text`** — was approved, now blocked. Every
  submitter-controlled field is screened.
- **PII reported as an attack** — a credit card number in a taxi receipt used to block
  the expense *and* be recorded as a prompt injection.
- **Dilution** — joining fields before scanning made a blocked injection pass. Screening
  is per field for that reason, and the reason is measured, not assumed.

---

## 3. The SRE

*Who gets paged when this misbehaves at 3am.*

| | Issue |
| :--- | :--- |
| 💸 | **No spend circuit breaker.** `FLEET_LIVE_AGENT=1` loops Gemini calls forever with nothing watching the budget. The only control is remembering to stop it. |
| 💸 | **Per-field screening tripled Model Armor calls** — up to 3 per report where it was 1. Correct, and worth knowing before pointing it at volume. |
| 🔁 | **No retry or backoff** on `stream_query`. A single transient 503 fails the whole review; `review_loop` prints and moves on. |
| 🧊 | **`records._all_records()` is `lru_cache`d forever.** A long-running server never sees a new report. Fine for a demo, wrong for a service. |
| 📈 | **`completedSpans` only ever appends.** A demo window is fine; an hour is not. |
| 🔍 | **`/healthz` doesn't report which mode is running.** Deterministic and live-agent are indistinguishable from outside, and they have wildly different cost profiles. |
| 🤫 | **`BatchSpanProcessor` swallows export failures.** Documented, still true: the fleet keeps running while the audit trail quietly stays empty. |

---

## 4. The finance reviewer

*The person who actually has to use this on Monday.*

This is the mindset the project has thought about least, and it is the one the track's
"Unlikely Hero" criterion is pointing at.

**Approve/Deny captures no identity and no reason.** `resolve_pending()` records the
decision and nothing else — not who made it, not why. For a *compliance* control that
is not a gap, it is disqualifying: the entire point of an approval workflow is
attribution, and an audit trail that cannot say who approved a $6,200 expense is not
an audit trail.

**The reviewer cannot see what was redacted.** DLP reports `redaction_count: 1` and the
reviewer is asked to approve without seeing what was removed or why. They are being
asked to trust the machine on exactly the thing they are there to check.

**There is no queue.** The radar is a beautiful monitoring surface and a poor work
surface. A reviewer needs "what is waiting for me", sorted by age, not a sweep line.

**Deny does nothing.** No notification, no reason back to the employee, no path to
resubmit. The system can say no and cannot explain it.

---

## 5. The staff engineer

*Reviewing this as a change they will have to maintain.*

**The eval does not test the shipped code.** `run_eval.py` imports
`from decision import decide` — that is `devtools/decision.py`. The deployed logic is
`fleet/policy.py`. **13/13 validates the stand-in**, and the two are kept in agreement
by hand.

**They have already drifted.** `policies/rules.yaml` gained `escalating_violations`;
`fleet/policy.py` reads it, and `devtools/rules_loader.py` — a hand-rolled parser that
does not do nested lists — silently drops the key:

```
devtools parser keys: ['allowed_categories', 'disallowed_categories',
                       'preapproval_required_above_usd', 'receipt_required_above_usd',
                       'violation_code_no_preapproval', 'violation_code_no_receipt']
escalating_violations present? False
```

Silent, because a missing key is indistinguishable from a key that isn't set. Two
engines both claim to read one config file and one of them cannot see half of it.

**Two verdict paths.** `orchestrator.decide()` and `live_agent._derive()` each derive a
verdict, each with their own escalation logic. They agree today. Nothing makes them.

**Tool names are magic strings in three files** — `invariants.REQUIRED_EVIDENCE`,
`tools.py`, `live_agent._tool_summary`. Rename a tool and the invariant silently stops
requiring it, which is the worst possible failure mode for a security check.

---

## Closed since this review

Everything below was fixed in `c898a53`, with the reproductions above kept as the
record of what the bug actually was.

| Finding | Now |
| :--- | :--- |
| Report-id spoofing | `records.identifies()` — the id must come with a matching amount, or every attestable field fails closed and `REPORT_ID_AMOUNT_MISMATCH` escalates |
| Invariants checked presence, not arguments | `Evidence.scanned_text` + `INJECTION_SCAN_INCOMPLETE`, naming the fields the scan never saw |
| `rules_loader` silently dropped keys | block lists are discovered, not listed |
| Eval tested the stand-in, not the shipped code | parity gate in `eval_claims`: 13/13 fixtures agree between `fleet/` and `devtools/` |
| Approve/Deny had no attribution | `approver` + `reason` on the span; an unattributed decision is marked `UNATTRIBUTED` rather than reading as signed-off |

Still open, and named in [EVALUATION.md](EVALUATION.md): the receipt total is not
reconciled, `approver` is unauthenticated, per-agent IAM is one identity, and the
multi-agent justification is a privilege split rather than a capability one.

---

## What this adds up to

Ranked by *what would actually hurt*, not by effort:

1. **Approval attribution** — who approved, and why. A compliance system without it is
   theatre, and it is the finance reviewer's first question.
2. **Report ids must be system-assigned.** The attestation layer is only as good as
   its key.
3. **Make the eval test the shipped code**, or delete the second rule engine. A green
   suite over a stand-in is how the first bug survived four days.
4. **Attest the amount** against the receipt total.
5. **Bind invariant evidence to arguments**, not just to the call.
6. **Re-time the demo** for the live-agent path before recording anything.

Items 1–5 are honest roadmap for a two-day deadline. **Item 6 is due before the video**,
and item 3 is a half-hour that removes a whole class of future surprise.
