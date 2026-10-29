"""Attacks on the gateway, each of which must be refused — and refused for the right
reason. Shared by local_server.py (which streams them to the radar as BLOCKED spans)
and run_security_checks.py (which asserts the reason), so the demo and the test cannot
drift into proving different things.

Each scenario names the README claim it backs. A scenario that gets *through* the
gateway is a failure of the gateway, not a demo with a surprising ending.
"""

import base64
import json

import agent_gateway
import agent_identity


def _forge_scope(token, scope):
    """Edit a genuine token's claims to grant an extra scope, keeping its signature."""
    body, sig = token.split(".", 1)
    claims = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    claims["scopes"] = sorted(set(claims["scopes"]) | {scope})
    forged = base64.urlsafe_b64encode(json.dumps(claims, separators=(",", ":")).encode()).rstrip(b"=").decode()
    return f"{forged}.{sig}"


SCENARIOS = [
    {
        "id": "SECURITY-DEMO-SCOPE-REDACT",
        "claim": "Screening cannot reach PII-redaction functions",
        "agent": "screening",
        "capability": "pii.redact",
        "expected_reason": "MISSING_SCOPE",
        "token": lambda: agent_identity.issue_token("screening"),
        "args": ("4111 1111 1111 1111",),
    },
    {
        "id": "SECURITY-DEMO-SCOPE-POLICY",
        "claim": "The PII agent cannot modify policy rules",
        "agent": "pii_compliance",
        "capability": "policy.write",
        "expected_reason": "MISSING_SCOPE",
        "token": lambda: agent_identity.issue_token("pii_compliance"),
        "args": (),
    },
    {
        "id": "SECURITY-DEMO-FORGED-TOKEN",
        "claim": "An agent cannot grant itself a scope",
        "agent": "screening",
        "capability": "policy.write",
        "expected_reason": "BAD_SIGNATURE",
        "token": lambda: _forge_scope(agent_identity.issue_token("screening"), "policy:write"),
        "args": (),
    },
    {
        "id": "SECURITY-DEMO-EXPIRED-TOKEN",
        "claim": "A stolen token stops working",
        "agent": "orchestrator",
        "capability": "screening.check_policy",
        "expected_reason": "TOKEN_EXPIRED",
        "token": lambda: agent_identity.issue_token("orchestrator", ttl_s=-5),
        "args": ({},),
    },
    {
        "id": "SECURITY-DEMO-UNKNOWN-CAPABILITY",
        "claim": "Nothing outside the registry is callable",
        "agent": "orchestrator",
        "capability": "payments.release",
        "expected_reason": "UNKNOWN_CAPABILITY",
        "token": lambda: agent_identity.issue_token("orchestrator"),
        "args": (),
    },
]


def attempt(scenario):
    """Run one scenario. Returns the GatewayDenied it raised, or None if the gateway
    wrongly let it through.
    """
    try:
        agent_gateway.invoke(scenario["token"](), scenario["capability"], *scenario["args"])
    except agent_gateway.GatewayDenied as denied:
        return denied
    except Exception:  # noqa: BLE001 - the handler ran, which means the gateway let it through
        return None
    return None
