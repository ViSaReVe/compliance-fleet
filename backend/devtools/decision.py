"""Single source of truth for turning a report into a verdict — shared by
local_server.py (which wraps this with span timing for the live radar) and
run_eval.py (which calls it directly against evals/eval_set.json). Keeping this in
one place means the two can't drift out of sync with each other.
"""

from pii_scan import detect_injection, redact
from rule_engine import check_policy, summarize


def screen(report, rules):
    """The screening.check_policy capability — only this piece needs policy rules."""
    return check_policy(report, rules)


def compliance_decide(report, violations):
    """The pii_compliance.decide capability — injection check, redaction, verdict.
    Deliberately takes already-computed violations rather than rules/report alone,
    so it has no access to raw policy thresholds — mirrors the README's "PII Agent
    cannot modify policy rules" boundary even in this local stand-in.
    """
    if detect_injection(report.get("description")):
        return {
            "verdict": "blocked",
            "violations": violations,
            "armor_verdict": "PROMPT_INJECTION_BLOCKED",
            "dlp_redactions": 0,
            "summary": f"Model Armor intercepted: \"{report['description']}\".",
        }

    combined_text = " ".join(filter(None, [report.get("receipt_ocr_text"), report.get("description")]))
    _, redaction_count = redact(combined_text)

    if "OVER_LIMIT_NO_PREAPPROVAL" in violations:
        verdict = "escalated"
    elif violations:
        verdict = "flagged"
    else:
        verdict = "approved"

    summary = summarize(report, violations)
    if redaction_count:
        summary = f"Redacted {redaction_count} item(s) before persistence. {summary}"

    return {
        "verdict": verdict,
        "violations": violations,
        "armor_verdict": None,
        "dlp_redactions": redaction_count,
        "summary": summary,
    }


def decide(report, rules):
    """Convenience composition of screen() + compliance_decide() for callers (like
    run_eval.py) that don't need the two capabilities gateway-mediated separately.
    """
    violations = screen(report, rules)
    return compliance_decide(report, violations)
