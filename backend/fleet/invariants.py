"""Invariants over a run's trace — the audit trail as a control, not just a record.

Every other guardrail here checks the *content* of a report. These check the *shape of
the run itself*: did the security steps actually happen, in an order that makes the
verdict mean anything?

That matters because of how agents fail. A `LlmAgent` told to call Model Armor first
will sometimes not call it and then write "Model Armor: Passed" anyway — the failure is
a missing step plus a confident sentence, and every content-level check downstream is
looking at the wrong thing. `verify_deployed` already refuses to read the agent's
prose as evidence. This goes further: **a verdict that lacks its supporting evidence
spans is not allowed to stand.**

    approved  requires  scan_for_prompt_injection, redact_pii, check_expense_policy
                        all present in this run's trace

Fail one and the run does not fail open, and does not fail shut either — it
**escalates to a human**, carrying a violation code naming what was missing. Which is
the honest answer for "the agent skipped a security step": nobody can safely
auto-approve that, and nobody should silently discard it either.

Where the evidence comes from matters, and differs by path:

  live agent path      the runtime's own `function_response` events — the agent
                       cannot forge these, because it does not write them. A tool it
                       claims to have called but did not leaves no response.
  deterministic path   the code itself, trusted by construction — it calls Model Armor
                       and Cloud DLP unconditionally and records that it did.

So on the path where the agent could lie, the evidence is not the agent's to write.
That is the whole design, and the same move [AgentArmor] makes in applying program
analysis to an agent's runtime trace rather than to its output.
"""

import dataclasses

# Tools whose evidence must be present in the trace before a verdict is trustworthy.
# Keyed by the verdicts they are required for — a run blocked at the boundary never
# reaches redaction or policy, so requiring them there would be nonsense.
REQUIRED_EVIDENCE = {
    "scan_for_prompt_injection": ("approved", "flagged", "escalated"),
    "redact_pii": ("approved", "flagged", "escalated"),
    "check_expense_policy": ("approved", "flagged", "escalated"),
}

MISSING_EVIDENCE_CODE = "MISSING_SECURITY_EVIDENCE"


@dataclasses.dataclass
class Evidence:
    """What a run's trace actually shows happened."""

    tools_called: frozenset = frozenset()
    armor_blocked: bool = False
    violations: tuple = ()
    # What was actually handed to the injection scanner. Presence of a call is not
    # enough: an agent that scans the merchant name and skips the description
    # satisfies "scan_for_prompt_injection was called" while scanning nothing that
    # mattered. The invariant has to bind to the argument, not to the call.
    scanned_text: str = ""

    @classmethod
    def from_tool_results(cls, tool_results, violations=(), scanned_text=""):
        """Build from the runtime's function_response payloads.

        A tool appears here only if the runtime returned a response for it, which it
        does only if the tool actually ran.
        """
        armor = (tool_results.get("scan_for_prompt_injection") or [{}])[0] or {}
        return cls(
            tools_called=frozenset(tool_results.keys()),
            armor_blocked=bool(armor.get("blocked")),
            violations=tuple(violations),
            scanned_text=scanned_text or "",
        )


# A field is considered scanned if this much of it made it to the guardrail. Not 100%:
# the agent may reasonably normalise whitespace or quote-wrap what it passes along.
COVERAGE_THRESHOLD = 0.8


def _covered(field_value, scanned_text):
    """Whether `field_value` plausibly reached the scanner inside `scanned_text`."""
    value = " ".join(str(field_value).split())
    if not value:
        return True
    haystack = " ".join(scanned_text.split())
    if value in haystack:
        return True
    # Fall back to token overlap, so a rewrapped or re-quoted copy still counts.
    tokens = value.split()
    if not tokens:
        return True
    hit = sum(1 for token in tokens if token in haystack)
    return hit / len(tokens) >= COVERAGE_THRESHOLD


def check(evidence, verdict, report=None):
    """Every invariant this run breaks, as violation codes. Empty means sound."""
    broken = []

    # Did the injection scan actually see the untrusted text? A call with the wrong
    # argument is not evidence of anything.
    if report is not None and "scan_for_prompt_injection" in evidence.tools_called:
        from . import policy

        unscanned = [
            field
            for field in policy.UNTRUSTED_FIELDS
            if report.get(field) and not _covered(report[field], evidence.scanned_text)
        ]
        if unscanned:
            broken.append(f"INJECTION_SCAN_INCOMPLETE:{','.join(unscanned)}")

    for tool, verdicts_requiring_it in REQUIRED_EVIDENCE.items():
        if verdict in verdicts_requiring_it and tool not in evidence.tools_called:
            broken.append(f"{MISSING_EVIDENCE_CODE}:{tool}")

    # A verdict that contradicts the evidence in the same trace. Neither of these
    # should be reachable through the normal path — which is exactly why they are
    # worth asserting, because the normal path is what an agent deviates from.
    if verdict == "approved" and evidence.armor_blocked:
        broken.append("APPROVED_DESPITE_ARMOR_BLOCK")

    if verdict == "approved" and any(
        code.startswith("UNVERIFIED_") for code in evidence.violations
    ):
        broken.append("APPROVED_OVER_UNVERIFIED_CLAIM")

    return broken


def enforce(evidence, verdict, violations=(), report=None):
    """Apply the invariants, returning the verdict that is actually supportable.

    Fails to a human rather than open or shut. An unsound run is not evidence that
    the expense is fraudulent — it is evidence that the machine's opinion of it is
    worthless, and a person should look.
    """
    broken = check(evidence, verdict, report)
    if not broken:
        return verdict, list(violations), []
    return "escalated", list(violations) + broken, broken


def describe(broken):
    """One line a human can act on, for the radar and the audit trail."""
    if not broken:
        return ""
    missing = [
        code.split(":", 1)[1]
        for code in broken
        if code.startswith(MISSING_EVIDENCE_CODE + ":")
    ]
    incomplete = [
        code.split(":", 1)[1]
        for code in broken
        if code.startswith("INJECTION_SCAN_INCOMPLETE:")
    ]
    if incomplete:
        return (
            f"Escalated: the injection scan never saw {', '.join(incomplete)}, so a "
            f"clean scan result proves nothing about it."
        )
    if missing:
        return (
            f"Escalated: the run never called {', '.join(missing)}, so its verdict "
            f"has no security evidence behind it."
        )
    return f"Escalated: {', '.join(broken)}."
