# ADR 0001: Paying an expense is a sibling pipeline, not another review step

## Status

Accepted. Implemented in `backend/devtools/` only; not on Google Cloud.

## Context

The fleet answered one question: is this expense acceptable? The next real-world step is
paying it. That tempts a third stage on the end of the review: screening, then compliance,
then "reimburse".

But the two jobs differ in everything that matters. A review is stateless and its worst
outcome is a wrong verdict. A payout has state (drafted, paid, cancelled), must never run
twice, and its worst outcome is money leaving. They also fail differently: a review that
cannot finish should go to a human; a payout that cannot finish must not guess.

## Decision

Build payout as its own pipeline with its own state machine (`payouts.py`) and its own
agent (`reimbursement`, risk level CRITICAL), sharing only the registry, identity and
gateway with the review. The structure follows the supply-replenishment workflow in the EIR
hospital-fleet project, which made the same call for the same reason.

Planning is event → capability, guarded by the case's status. `ExpenseApproved` plans a
draft only if none exists; `PayoutDrafted` plans a settlement only while the case is still
`drafted`. A replayed event therefore plans nothing, so it cannot pay twice.

The amount that decides whether a person must approve lives in the payout ledger, set once
at draft time. The gateway reads it from there, not from anything the caller passes. This is
the lesson of our own `records.py` bug: a value that decides whether a human looks is not a
value the caller supplies.

## Consequences

- A change to payouts cannot regress the review path, and the review's 13/13 eval is
  untouched by it.
- Some duplication in how the two pipelines park for a human. That is accepted until a
  third pipeline shows what they genuinely share.
- Payout spans ride on the *same trace* as the review (same `report_id`), so one reasoning
  chain reads screening → compliance → draft → authorization → paid.
- The radar needed a fourth node. It sits beside the review triangle, not in it, because it
  is a different job and not another stage.
- Everything is a synthetic ledger. No money moves.
