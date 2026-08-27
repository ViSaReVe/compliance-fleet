"""Local proof of the README's Agent Gateway + Agent Identity story: "Screening Agent
cannot read PII-redaction functions, PII Agent cannot modify policy rules" and
"a thin API layer... enforcing who can call whom." No real Cloud Run service accounts
or IAM bindings here — this is a plain allowlist standing in for that until Vidya
wires real per-agent identities. What IS real: every capability call in
local_server.py's normal flow actually goes through gateway_call(), and an
out-of-policy call actually gets refused, not just documented as a rule.
"""

# capability -> agents allowed to invoke it. Everything else is implicitly denied.
ALLOWED_CALLERS = {
    "screening.check_policy": {"orchestrator"},
    "pii_compliance.decide": {"orchestrator"},
}


class GatewayDenied(Exception):
    def __init__(self, caller, capability):
        self.caller = caller
        self.capability = capability
        super().__init__(f"{caller} is not authorized to call {capability}")


def gateway_call(caller, capability, fn, *args, **kwargs):
    allowed = ALLOWED_CALLERS.get(capability, set())
    if caller not in allowed:
        raise GatewayDenied(caller, capability)
    return fn(*args, **kwargs)
