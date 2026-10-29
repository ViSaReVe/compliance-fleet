"""Local stand-in for Agent Gateway: the one door every inter-agent call goes through.

The earlier version of this file was a hardcoded {capability: {callers}} dict keyed on
a caller *name* the caller supplied itself — which proves nothing, since anything can
claim to be "orchestrator". This version makes the claim checkable. A call is only
let through when all of these hold, checked in this order:

  1. the token verifies          (agent_identity.verify_token: signature + expiry)
  2. the capability is cataloged (agent_registry.resolve: unknown -> refused)
  3. the capability's owning agent is routable (active, not unavailable)
  4. the token carries the scope the registry says that capability requires
  5. if the capability needs a human (e.g. spending money), a valid approval grant
     accompanies the call: signed, unexpired, for *this* capability and *this* subject,
     and not already used

Check 5 has two outcomes on purpose. No grant at all is not an attack — it is the normal
"park this for a person" path, so it raises ApprovalRequired and is audited as such. A
grant that is forged, expired, for something else, or replayed *is* an attack and is
refused like any other. Each refusal has a distinct `reason`, so a denial says *why* rather than just "no".
Every decision, allowed or not, lands in an audit log. Real GEAP runs this as a
managed gateway with IAP enforcement; the checks are the same, the enforcement
point here is just a function.
"""

import collections
import threading
import time

import agent_identity
import agent_registry

_AUDIT = collections.deque(maxlen=500)
_AUDIT_LOCK = threading.Lock()
_USED_APPROVALS = set()


class ApprovalRequired(Exception):
    """The call is permitted but must wait for a human. Not a denial."""

    def __init__(self, caller, capability, subject=None):
        self.caller = caller
        self.capability = capability
        self.subject = subject
        super().__init__(f"{caller} -> {capability} is parked: a human must approve it first")


class GatewayDenied(Exception):
    def __init__(self, caller, capability, reason, detail=""):
        self.caller = caller
        self.capability = capability
        self.reason = reason
        self.detail = detail
        super().__init__(f"{caller} -> {capability} refused: {reason}" + (f" ({detail})" if detail else ""))


def _record(caller, capability, allowed, reason, approver=None):
    with _AUDIT_LOCK:
        _AUDIT.append(
            {
                "ts_ms": int(time.time() * 1000),
                "caller": caller,
                "capability": capability,
                "allowed": allowed,
                "reason": reason,
                **({"approver": approver} if approver else {}),
            }
        )


def _deny(caller, capability, reason, detail=""):
    _record(caller, capability, False, reason)
    raise GatewayDenied(caller, capability, reason, detail)


def invoke(token, capability, *args, approval=None, subject=None, **kwargs):
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

    if not agent_registry.is_available(entry["owner"]):
        _deny(caller, capability, "AGENT_UNAVAILABLE", f"{entry['owner']} is not routable right now")

    if entry["scope"] not in claims["scopes"]:
        _deny(
            caller,
            capability,
            "MISSING_SCOPE",
            f"{capability} requires {entry['scope']!r}; {caller} holds {claims['scopes']}",
        )

    approver = None
    needs_human = entry["requires_approval"]
    if needs_human is not None and needs_human(*args, **kwargs):
        if approval is None:
            _record(caller, capability, False, "APPROVAL_REQUIRED")
            raise ApprovalRequired(caller, capability, subject)
        try:
            grant = agent_identity.verify_approval(approval, capability, subject)
        except agent_identity.IdentityError as err:
            _deny(caller, capability, err.reason, err.detail)
        with _AUDIT_LOCK:
            replayed = grant["jti"] in _USED_APPROVALS
            if not replayed:
                _USED_APPROVALS.add(grant["jti"])
        if replayed:
            _deny(caller, capability, "APPROVAL_USED", "this approval has already been spent")
        approver = grant["approver"]

    _record(caller, capability, True, "OK", approver=approver)
    return entry["handler"](*args, **kwargs)


def audit_log():
    with _AUDIT_LOCK:
        return list(_AUDIT)
