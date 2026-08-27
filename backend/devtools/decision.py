"""Single source of truth for turning a report into a verdict — shared by
local_server.py (which wraps this with span timing for the live radar) and
run_eval.py (which calls it directly against evals/eval_set.json). Keeping this in
one place means the two can't drift out of sync with each other.
"""

from pii_scan import detect_injection, redact
from rule_engine import check_policy, summarize


def decide(report, rules):
    violations = check_policy(report, rules)

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
