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
    "orchestrator": {"invoke:screening", "invoke:pii_compliance", "invoke:reimbursement"},
    "screening": {"policy:read"},
    "pii_compliance": {"pii:redact"},
    # Only the reimbursement agent can move money, and even it needs a human's grant
    # for anything over the authorization threshold — see issue_approval().
    "reimbursement": {"payout:execute"},
}

APPROVAL_TTL_S = 300

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
        "typ": "access",
        "sub": spiffe_id(agent),
        "agent": agent,
        "scopes": sorted(GRANTS[agent]),
        "iat": now,
        "exp": now + ttl_s,
        "jti": uuid.uuid4().hex,
    }
    body = _b64(json.dumps(claims, separators=(",", ":")).encode("utf-8"))
    return f"{body}.{_sign(body)}"


def _verify(token, typ):
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

    # An approval grant must not pass as an access token, nor the reverse — both are
    # signed with the same key, so the type is what keeps them apart.
    if claims.get("typ") != typ:
        raise IdentityError("WRONG_TOKEN_TYPE", f"expected a {typ} token, got {claims.get('typ')!r}")

    if claims.get("exp", 0) < time.time():
        what = f"token for {claims.get('agent')!r}" if typ == "access" else "approval"
        reason = "TOKEN_EXPIRED" if typ == "access" else "APPROVAL_EXPIRED"
        raise IdentityError(reason, f"{what} is past its expiry")
    return claims


def verify_token(token):
    return _verify(token, "access")


def issue_approval(capability, subject, approver, reason=None, ttl_s=APPROVAL_TTL_S):
    """A human's decision, as something the gateway can check.

    Bound to one capability and one subject (the payout, not just "any payout") and
    to a named approver, so a grant cannot be reused for a different payment or issued
    anonymously. The gateway additionally treats each grant as single-use. An approval
    without a name is refused here, because spending money without knowing who said yes
    is the audit-trail gap docs/REVIEW.md calls disqualifying.
    """
    if not approver or not str(approver).strip():
        raise IdentityError("APPROVER_REQUIRED", "an approval must name who approved it")
    now = int(time.time())
    claims = {
        "typ": "approval",
        "cap": capability,
        "sub": subject,
        "approver": str(approver).strip(),
        "reason": reason,
        "iat": now,
        "exp": now + ttl_s,
        "jti": uuid.uuid4().hex,
    }
    body = _b64(json.dumps(claims, separators=(",", ":")).encode("utf-8"))
    return f"{body}.{_sign(body)}"


def verify_approval(token, capability, subject):
    claims = _verify(token, "approval")
    if claims.get("cap") != capability or claims.get("sub") != subject:
        raise IdentityError(
            "APPROVAL_MISMATCH",
            f"approval is for {claims.get('cap')!r} on {claims.get('sub')!r}, not {capability!r} on {subject!r}",
        )
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
