"""Local stand-in for Agent Registry: a catalog the Orchestrator queries at runtime
instead of holding references to the agents it calls.

Real GEAP registers each agent as an A2A service from an agent card and lets callers
search the catalog. This keeps the same two ideas with no cloud behind it:

  * agent cards  — name, version, description, endpoint, identity, skills
  * capabilities — the callable surface, each with the scope required to invoke it

The Orchestrator resolves "screening.check_policy" through here and never imports the
screening function. Adding a capability to an agent therefore changes the catalog and
the scope requirement in one place; nothing downstream can call it without both.

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


def register_agent(name, description, version="1.0.0"):
    _AGENTS[name] = {
        "name": name,
        "description": description,
        "version": version,
        "url": f"local://{name}",
        "identity": agent_identity.spiffe_id(name),
        "skills": [],
    }


def register_capability(capability, *, owner, scope, handler, kind):
    """Add a callable to the catalog. `owner` must already be a registered agent; an
    agent_skill is also listed on that agent's card so the card and the catalog agree.
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
        {k: v for k, v in cap.items() if k != "handler"}
        for cap in _CAPABILITIES.values()
    ]
