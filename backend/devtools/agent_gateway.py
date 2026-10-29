"""Local stand-in for Agent Gateway: the one door every inter-agent call goes through.

The earlier version of this file was a hardcoded {capability: {callers}} dict keyed on
a caller *name* the caller supplied itself — which proves nothing, since anything can
claim to be "orchestrator". This version makes the claim checkable. A call is only
let through when all of these hold, checked in this order:

  1. the token verifies          (agent_identity.verify_token: signature + expiry)
  2. the capability is cataloged (agent_registry.resolve: unknown -> refused)
  3. the token carries the scope the registry says that capability requires

Each refusal has a distinct `reason`, so a denial says *why* rather than just "no".
Every decision, allowed or not, lands in an audit log. Real GEAP runs this as a
managed gateway with IAP enforcement; the three checks are the same, the enforcement
point here is just a function.
"""

import collections
import threading
import time

import agent_identity
import agent_registry

_AUDIT = collections.deque(maxlen=500)
_AUDIT_LOCK = threading.Lock()


class GatewayDenied(Exception):
    def __init__(self, caller, capability, reason, detail=""):
        self.caller = caller
        self.capability = capability
        self.reason = reason
        self.detail = detail
        super().__init__(f"{caller} -> {capability} refused: {reason}" + (f" ({detail})" if detail else ""))


def _record(caller, capability, allowed, reason):
    with _AUDIT_LOCK:
        _AUDIT.append(
            {
                "ts_ms": int(time.time() * 1000),
                "caller": caller,
                "capability": capability,
                "allowed": allowed,
                "reason": reason,
            }
        )


def _deny(caller, capability, reason, detail=""):
    _record(caller, capability, False, reason)
    raise GatewayDenied(caller, capability, reason, detail)


def invoke(token, capability, *args, **kwargs):
    try:
        claims = agent_identity.verify_token(token)
    except agent_identity.IdentityError as err:
        # The token failed verification, so its claimed agent name is untrusted — it is
        # used only to label the denial, never to decide it.
        caller = f"{agent_identity.peek_agent(token)} (unverified)"
        _deny(caller, capability, err.reason, err.detail)

    caller = claims["agent"]

    try:
        entry = agent_registry.resolve(capability)
    except LookupError:
        _deny(caller, capability, "UNKNOWN_CAPABILITY", "not in the agent registry")

    if entry["scope"] not in claims["scopes"]:
        _deny(
            caller,
            capability,
            "MISSING_SCOPE",
            f"{capability} requires {entry['scope']!r}; {caller} holds {claims['scopes']}",
        )

    _record(caller, capability, True, "OK")
    return entry["handler"](*args, **kwargs)


def audit_log():
    with _AUDIT_LOCK:
        return list(_AUDIT)
