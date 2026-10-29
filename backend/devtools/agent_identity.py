"""Local stand-in for Agent Identity: every agent has its own identity and the least
scope it needs, and proves it with a signed, short-lived token.

Real GEAP gives each deployed agent a SPIFFE identity bound to its mTLS certificate
and scoped through IAM. This is the same shape with no cloud behind it: a SPIFFE-style
id per agent, a table of granted scopes, and HMAC-signed tokens the gateway can verify.
The signing key is generated per process and never leaves it, so a token cannot be
forged or edited by anything that does not hold the key — see run_security_checks.py,
which tries both.

Scopes are deliberately fine-grained and non-overlapping: `policy:read` belongs to
Screening alone, `pii:redact` to PII/Compliance alone, and `policy:write` to nobody.
That last one is the point of "the PII agent cannot modify policy rules": there is no
identity in the system that holds the scope, so no token can ever carry it.
"""

import base64
import hashlib
import hmac
import json
import os
import time
import uuid

TRUST_DOMAIN = "compliance-fleet.local"
DEFAULT_TTL_S = 60

# agent -> scopes it holds. Anything not listed here is not granted.
GRANTS = {
    "orchestrator": {"invoke:screening", "invoke:pii_compliance"},
    "screening": {"policy:read"},
    "pii_compliance": {"pii:redact"},
}

_SIGNING_KEY = os.urandom(32)


class IdentityError(Exception):
    def __init__(self, reason, detail=""):
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason}: {detail}" if detail else reason)


def spiffe_id(agent):
    return f"spiffe://{TRUST_DOMAIN}/agent/{agent}"


def _b64(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _unb64(text):
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(body):
    return _b64(hmac.new(_SIGNING_KEY, body.encode("ascii"), hashlib.sha256).digest())


def issue_token(agent, ttl_s=DEFAULT_TTL_S):
    if agent not in GRANTS:
        raise IdentityError("UNKNOWN_AGENT", f"no identity is provisioned for {agent!r}")
    now = int(time.time())
    claims = {
        "sub": spiffe_id(agent),
        "agent": agent,
        "scopes": sorted(GRANTS[agent]),
        "iat": now,
        "exp": now + ttl_s,
        "jti": uuid.uuid4().hex,
    }
    body = _b64(json.dumps(claims, separators=(",", ":")).encode("utf-8"))
    return f"{body}.{_sign(body)}"


def verify_token(token):
    try:
        body, sig = token.split(".", 1)
    except (AttributeError, ValueError):
        raise IdentityError("MALFORMED_TOKEN", "expected <claims>.<signature>") from None

    if not hmac.compare_digest(sig, _sign(body)):
        raise IdentityError("BAD_SIGNATURE", "token was not signed by this fleet's identity authority")

    try:
        claims = json.loads(_unb64(body))
    except (ValueError, UnicodeDecodeError):
        raise IdentityError("MALFORMED_TOKEN", "claims are not valid JSON") from None

    if claims.get("exp", 0) < time.time():
        raise IdentityError("TOKEN_EXPIRED", f"token for {claims.get('agent')!r} is past its expiry")
    return claims


def peek_agent(token):
    """The agent a token *claims* to be, without trusting it. Only for labelling a
    denial — never for deciding anything.
    """
    try:
        body = token.split(".", 1)[0]
        return json.loads(_unb64(body)).get("agent", "unknown")
    except (AttributeError, ValueError, UnicodeDecodeError):
        return "unknown"
