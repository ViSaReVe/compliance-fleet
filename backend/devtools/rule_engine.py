"""Pure policy rule-check — the part of backend/fleet/screening.py that doesn't need
Gemini. Real screening.py also has to *extract* amount/category/date/merchant from
free text via an LLM call; here that step is skipped because the fixtures are already
structured JSON, so this only proves the rule-matching logic against policies/rules.yaml.
"""


def check_policy(report, rules):
    violations = []

    amount = report["amount_usd"]
    receipt_cap = rules["receipt_required_above_usd"]
    if amount > receipt_cap and not report.get("receipt_attached"):
        violations.append(rules["violation_code_no_receipt"])

    preapproval_cap = rules["preapproval_required_above_usd"]
    if amount > preapproval_cap and not report.get("requested_preapproval"):
        violations.append(rules["violation_code_no_preapproval"])

    disallowed = rules.get("disallowed_categories") or []
    if report.get("category") in disallowed:
        violations.append("DISALLOWED_CATEGORY")

    return violations


def summarize(report, violations):
    if not violations:
        return f"${report['amount_usd']:.0f} within policy."
    if "OVER_LIMIT_NO_PREAPPROVAL" in violations:
        return f"${report['amount_usd']:.0f} exceeds pre-approval threshold with none requested."
    if "OVER_LIMIT_NO_RECEIPT" in violations:
        return f"${report['amount_usd']:.0f} exceeds receipt-free cap with no receipt attached."
    return ", ".join(violations)
