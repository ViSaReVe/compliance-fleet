"""Local stand-in for Agent Registry: a catalog the Orchestrator queries at runtime
instead of holding references to the agents it calls.

Real GEAP registers each agent as an A2A service from an agent card and lets callers
search the catalog. This keeps the same two ideas with no cloud behind it:

  * agent cards  — name, version, description, endpoint, identity, skills
  * capabilities — the callable surface, each with the scope required to invoke it

The Orchestrator resolves "screening.check_policy" through here and never imports the
screening function. Adding a capability to an agent therefore changes the catalog and
the scope requirement in one place; nothing downstream can call it without both.

Cards also carry what an operator needs to route around trouble — risk level,
lifecycle, health, and a fallback agent — plus `granted_scopes`, kept separate from the
skills an agent *offers*. What an agent can do for others and what it may itself call
are different questions, and conflating them is how least-privilege quietly erodes.
(The shape is borrowed from the agent descriptors in the EIR hospital-fleet project.)

Capabilities cover two kinds of thing: an agent's own skills (`agent_skill`) and the
platform tools an agent reaches for (`tool` — reading policy, redacting PII). Tools get
registered too, so reading the policy file needs a scope exactly like calling an agent.
"""

import agent_identity

_AGENTS = {}
_CAPABILITIES = {}


def reset():
    _AGENTS.clear()
    _CAPABILITIES.clear()


RISK_LEVELS = ("LOW", "MEDIUM", "HIGH", "CRITICAL")
HEALTH_STATES = ("healthy", "degraded", "unavailable")
LIFECYCLES = ("active", "deprecated", "disabled")


def register_agent(name, description, version="1.0.0", risk_level="LOW", fallback_agent=None):
    if risk_level not in RISK_LEVELS:
        raise ValueError(f"risk_level must be one of {RISK_LEVELS}")
    _AGENTS[name] = {
        "name": name,
        "description": description,
        "version": version,
        "url": f"local://{name}",
        "identity": agent_identity.spiffe_id(name),
        "risk_level": risk_level,
        "lifecycle": "active",
        "health": "healthy",
        "fallback_agent": fallback_agent,
        "granted_scopes": sorted(agent_identity.GRANTS.get(name, ())),
        "skills": [],
    }


def set_health(name, health):
    if health not in HEALTH_STATES:
        raise ValueError(f"health must be one of {HEALTH_STATES}")
    _AGENTS[name]["health"] = health


def set_lifecycle(name, lifecycle):
    if lifecycle not in LIFECYCLES:
        raise ValueError(f"lifecycle must be one of {LIFECYCLES}")
    _AGENTS[name]["lifecycle"] = lifecycle


def is_available(name):
    """Routable: active, and not reporting itself unavailable. A degraded agent still
    takes calls — degraded is a warning to an operator, unavailable is a refusal.
    """
    card = _AGENTS.get(name)
    return bool(card) and card["lifecycle"] == "active" and card["health"] != "unavailable"


def register_capability(capability, *, owner, scope, handler, kind, requires_approval=None):
    """Add a callable to the catalog. `owner` must already be a registered agent; an
    agent_skill is also listed on that agent's card so the card and the catalog agree.

    `requires_approval` is an optional predicate over the call's arguments. When it says
    yes, the gateway refuses to run the capability without a human's approval grant —
    this is where "the agent may draft but a person authorizes" is enforced rather than
    asked for. A predicate rather than a flag because whether a payout needs a human
    depends on how big it is.
    """
    if kind not in ("agent_skill", "tool"):
        raise ValueError(f"unknown capability kind {kind!r}")
    if owner not in _AGENTS:
        raise LookupError(f"cannot register {capability!r}: owner {owner!r} is not a registered agent")

    _CAPABILITIES[capability] = {
        "capability": capability,
        "owner": owner,
        "scope": scope,
        "kind": kind,
        "handler": handler,
        "requires_approval": requires_approval,
    }
    if kind == "agent_skill":
        _AGENTS[owner]["skills"].append({"id": capability, "scope": scope})


def resolve(capability):
    try:
        return _CAPABILITIES[capability]
    except KeyError:
        raise LookupError(f"{capability!r} is not in the registry") from None


def find_agent(name):
    return _AGENTS.get(name)


def list_agents():
    return [dict(card, skills=list(card["skills"])) for card in _AGENTS.values()]


def list_capabilities():
    """Catalog view with the handler stripped — safe to serialize and show."""
    return [
        {
            **{k: v for k, v in cap.items() if k not in ("handler", "requires_approval")},
            "human_approval": cap["requires_approval"] is not None,
        }
        for cap in _CAPABILITIES.values()
    ]
