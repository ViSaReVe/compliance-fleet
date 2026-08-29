"""The system of record — the one source of attestable facts about a report.

Why this module exists, in one sentence: **policy thresholds being enforced in code
is worthless if the inputs to those thresholds come from the text being judged.**

The fleet's original design put the model in charge of extracting every field,
including `receipt_attached` and `requested_preapproval`, and then fed those into a
deterministic rule engine. That reads as safe — the thresholds are in Python, nobody
can argue them into changing — but it is not, and the deployed engine proved it.
Three runs each, all identical:

    "$840 hotel. The receipt is already attached in the expense system."
        -> receipt_attached=True -> violations [] -> APPROVED

    "$6,200 offsite. Pre-approved by the CFO last month under ticket PA-4471."
        -> requested_preapproval=True -> no OVER_LIMIT_NO_PREAPPROVAL -> never escalated

Model Armor does not fire on either, and it is right not to: there is no injection
phrasing to detect. This is not an injection attack. It is an ordinary lie, and it
lands in the gap between a guardrail that inspects *phrasing* and a rule engine that
trusts its *inputs*. The submitter does not need to change the rules if they can
change what the rules are shown.

So: whether a receipt exists is a fact about the expense system, not a reading of a
sentence. Same for pre-approval. Those come from here, and the model's account of
them is treated as a *claim* to be checked against the record — never as the input to
the check. This is the data-flow half of the control-flow argument the README already
makes, and the same principle CaMeL applies to tool-using agents: untrusted text may
influence data, never the values that decide an action.

`fixtures/reports/` stands in for the expense system's database. In production this
is a query against the receipts table and the approvals table; the boundary is what
matters, not the storage.
"""

import functools
import json

from . import config

# Fields a submitter must never be able to assert into existence by writing a
# sentence. Everything else (amount, category, merchant, date) is genuinely free
# text and is the model's job to extract.
ATTESTABLE_FIELDS = ("receipt_attached", "requested_preapproval")


@functools.lru_cache(maxsize=1)
def _all_records():
    records = {}
    for path in sorted(config.FIXTURES_DIR.glob("*.json")):
        with open(path, "r", encoding="utf-8") as f:
            report = json.load(f)
        if report.get("report_id"):
            records[report["report_id"]] = report
    return records


def lookup(report_id):
    """The recorded truth for one report, or None if the system has no such report."""
    if not report_id:
        return None
    return _all_records().get(report_id.strip())


def attested(report_id):
    """Attestable facts for a report, resolved from the record.

    **Fails closed.** An unknown report id yields False for every attestable field
    rather than deferring to whatever the text claimed — an id the expense system has
    never heard of is the weakest possible evidence that a receipt exists, not a
    reason to take the submitter's word for it.
    """
    record = lookup(report_id) or {}
    return {field: bool(record.get(field)) for field in ATTESTABLE_FIELDS}


def contradictions(report_id, claims):
    """Fields where the submission claims True but the record says otherwise.

    Returned as codes rather than prose because they become policy violations, and a
    violation code is something the rule engine can act on and the radar can render.
    A contradiction is deliberately *not* treated as fraud — it is treated as a
    reason a human should look, which is exactly what escalation is for.
    """
    truth = attested(report_id)
    found = []
    for field in ATTESTABLE_FIELDS:
        if claims.get(field) and not truth[field]:
            found.append(f"UNVERIFIED_{field.upper()}_CLAIM")
    return found
