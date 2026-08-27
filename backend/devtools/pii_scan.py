"""Local stand-in for Model Armor (injection detection) + Cloud DLP (redaction).
Regex-only, no API calls, no cost. NOT the real security boundary — this exists so the
orchestration + telemetry pipeline can be exercised end-to-end before Vidya wires the
real `gcloud model-armor` template and `dlp.deidentify_content` call (see README
Engineering notes: "Model Armor does not redact PII... Cloud DLP does"). Replace this
whole module with backend/fleet/compliance.py once those exist.
"""

import re

CARD_NUMBER_RE = re.compile(r"\b(?:\d[ -]?){13,16}\b")
SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")

# Deliberately naive keyword match, not a real jailbreak/injection classifier.
INJECTION_PHRASES = ("ignore policy", "ignore previous instructions", "auto-approve this")


def detect_injection(text):
    lowered = (text or "").lower()
    for phrase in INJECTION_PHRASES:
        if phrase in lowered:
            return True
    return False


def redact(text):
    if not text:
        return text, 0
    redacted, n1 = CARD_NUMBER_RE.subn("[REDACTED_CARD]", text)
    redacted, n2 = SSN_RE.subn("[REDACTED_SSN]", redacted)
    return redacted, n1 + n2
