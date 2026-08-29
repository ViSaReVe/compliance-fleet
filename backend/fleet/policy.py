"""Policy rules, loaded from policies/rules.yaml.

backend/devtools/rules_loader.py hand-parses this file because the devtools tree
carries no dependencies. The fleet has requirements.txt, so it uses PyYAML.
The rule-check logic itself is ported unchanged from devtools/rule_engine.py — it
is already validated by the 13-case eval set, so there is nothing to improve here.
"""

import functools

import yaml

from . import config


@functools.lru_cache(maxsize=1)
def load_rules():
    with open(config.POLICY_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# Every field a submitter can influence. Model Armor must see all of it, not just
# the description: an identical injection string was BLOCKED in `description` and
# APPROVED when moved into `receipt_ocr_text`, because only the description was ever
# scanned. Receipt OCR is the textbook indirect-injection vector — it is attacker-
# supplied document text that the system reads as data.
UNTRUSTED_FIELDS = ("description", "receipt_ocr_text", "merchant")


def untrusted_text(report):
    """Everything the submitter wrote, joined, for the guardrail to inspect."""
    return "\n".join(
        str(report.get(field)) for field in UNTRUSTED_FIELDS if report.get(field)
    )


def check_policy(report, rules=None):
    """Return the list of violation codes a report triggers. Pure, no I/O."""
    rules = rules or load_rules()
    violations = []

    amount = report["amount_usd"]

    if amount > rules["receipt_required_above_usd"] and not report.get("receipt_attached"):
        violations.append(rules["violation_code_no_receipt"])

    if amount > rules["preapproval_required_above_usd"] and not report.get("requested_preapproval"):
        violations.append(rules["violation_code_no_preapproval"])

    if report.get("category") in (rules.get("disallowed_categories") or []):
        violations.append("DISALLOWED_CATEGORY")

    return violations


UNVERIFIED_CLAIM_SUMMARY = {
    "UNVERIFIED_RECEIPT_ATTACHED_CLAIM":
        "the submission states a receipt is attached; the expense system has none on file",
    "UNVERIFIED_REQUESTED_PREAPPROVAL_CLAIM":
        "the submission states pre-approval was obtained; the approvals record shows none",
}


def escalates(violations):
    """Whether these violations need a human rather than an automatic verdict."""
    escalating = load_rules().get("escalating_violations") or ["OVER_LIMIT_NO_PREAPPROVAL"]
    return any(code in escalating for code in violations)


def summarize(report, violations):
    amount = f"${report['amount_usd']:.0f}"
    if not violations:
        return f"{amount} within policy."

    # An unverified claim leads, because it is the finding a human most needs to see —
    # a threshold breach is arithmetic, a contradicted claim is a judgement call.
    for code, reason in UNVERIFIED_CLAIM_SUMMARY.items():
        if code in violations:
            return f"{amount} escalated: {reason}."

    if "OVER_LIMIT_NO_PREAPPROVAL" in violations:
        return f"{amount} exceeds pre-approval threshold with none requested."
    if "OVER_LIMIT_NO_RECEIPT" in violations:
        return f"{amount} exceeds receipt-free cap with no receipt attached."
    return ", ".join(violations)
