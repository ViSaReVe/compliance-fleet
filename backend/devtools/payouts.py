"""The second pipeline: paying out an approved expense.

Expense review decides *whether* a report is acceptable. Paying it is a different job
with a different state machine and a different risk — it moves money — so it is a
sibling pipeline, not another step bolted onto the review. It shares the registry,
identity, and gateway with the first one and nothing else. (The structure follows the
supply-replenishment workflow in the EIR hospital-fleet project, which made the same
call for the same reason: two workflows whose guard conditions differ should not share
a state machine until there is a third that shows what they have in common.)

Two things worth the reader's attention:

  * The amount a payout is for lives *here*, in the system of record, set once when the
    payout is drafted. The gateway's "does this need a human?" check reads it from
    here, not from anything the caller passes. Same lesson as records.py in the real
    fleet: a value that decides whether a person looks is not a value a caller supplies.
  * Planning is event -> capability, guarded by the case's current status, so replaying
    an event is safe. A replayed "PayoutDrafted" after the payout was made plans
    nothing — it cannot pay twice. run_payout_checks.py replays on purpose.

Everything is a synthetic ledger. No money moves.
"""

import threading

AUTHORIZATION_THRESHOLD_USD = 500  # payouts above this need a named human to authorize

DRAFTED = "drafted"
PAID = "paid"
CANCELLED = "cancelled"

EVENT_TO_CAPABILITY = {
    "ExpenseApproved": "reimbursement.draft",
    "PayoutDrafted": "reimbursement.settle",
}

_CASES = {}
_LOCK = threading.Lock()


def reset():
    with _LOCK:
        _CASES.clear()


def payout_id_for(report_id):
    return f"PAY-{report_id}"


def plan_capability(event_type, report_id):
    """What should happen next for this report's payout, or None if nothing should.

    None is a real answer, and the important one: it is what makes a replayed event
    harmless instead of a duplicate payment.
    """
    capability = EVENT_TO_CAPABILITY.get(event_type)
    if capability is None:
        return None
    with _LOCK:
        case = _CASES.get(payout_id_for(report_id))
    if event_type == "ExpenseApproved":
        return capability if case is None else None
    if event_type == "PayoutDrafted":
        return capability if case is not None and case["status"] == DRAFTED else None
    return None


def draft(report):
    payout_id = payout_id_for(report["report_id"])
    with _LOCK:
        if payout_id in _CASES:
            return dict(_CASES[payout_id])
        _CASES[payout_id] = {
            "payout_id": payout_id,
            "report_id": report["report_id"],
            "amount_usd": float(report["amount_usd"]),
            "payee": f"employee:{report.get('submitted_by') or 'unknown'}",
            "status": DRAFTED,
        }
        return dict(_CASES[payout_id])


def needs_authorization(payout_id):
    with _LOCK:
        case = _CASES.get(payout_id)
    return bool(case) and case["amount_usd"] > AUTHORIZATION_THRESHOLD_USD


def execute(payout_id):
    """Make the payment. Idempotent: a second call reports `already_paid` and changes
    nothing, so no path through the system can pay one case twice.
    """
    with _LOCK:
        case = _CASES.get(payout_id)
        if case is None:
            raise LookupError(f"{payout_id} was never drafted")
        if case["status"] == CANCELLED:
            raise RuntimeError(f"{payout_id} was cancelled and cannot be paid")
        if case["status"] == PAID:
            return {**case, "already_paid": True}
        case["status"] = PAID
        return {**case, "already_paid": False}


def cancel(payout_id):
    with _LOCK:
        case = _CASES.get(payout_id)
        if case is None or case["status"] == PAID:
            return False
        case["status"] = CANCELLED
        return True


def get(payout_id):
    with _LOCK:
        case = _CASES.get(payout_id)
        return dict(case) if case else None
