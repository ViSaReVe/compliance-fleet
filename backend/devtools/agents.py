"""The three agents, wired through the registry, identity, and gateway.

bootstrap() is the whole provisioning step: it registers each agent and every
capability with the scope it needs. After that nothing calls a function directly —
the Orchestrator asks the gateway for a capability by name, the gateway checks the
caller's token against the registry, and only then does the handler run.

Each handler below acts as *its own* agent: it takes its own token and reaches for
what it needs through the gateway. So Screening reads policy because it holds
`policy:read`, and PII/Compliance redacts because it holds `pii:redact` — neither
works for the other, which is what the denial demos in security_demos.py prove.
"""

import agent_gateway
import agent_identity
import agent_registry
import payouts
from decision import compliance_decide, screen
from pii_scan import redact
from rules_loader import load_rules


def bootstrap(rules_path):
    agent_registry.reset()

    payouts.reset()

    # Risk levels say how much damage a wrong action does, which is what an operator
    # needs to see before deciding how closely to watch an agent.
    agent_registry.register_agent(
        "orchestrator",
        "Sequences the review: resolves agents from the registry and calls them through the gateway.",
        risk_level="MEDIUM",
    )
    agent_registry.register_agent(
        "screening", "Checks an expense report against policy rules and returns violations.", risk_level="LOW"
    )
    agent_registry.register_agent(
        "pii_compliance", "Screens for injection, redacts PII, and issues the final verdict.", risk_level="HIGH"
    )
    agent_registry.register_agent(
        "reimbursement",
        "Drafts and settles the payout for an approved expense. The only agent that can move money.",
        risk_level="CRITICAL",
    )

    def read_policy():
        return load_rules(rules_path)

    def write_policy(*_args, **_kwargs):
        # Registered so the capability exists and is refused on *scope*, not on being
        # unknown. No identity is granted policy:write, so reaching this is a gateway bug.
        raise RuntimeError("policy.write has no grantee; the gateway should never let a call get here")

    def screening_check(report):
        token = agent_identity.issue_token("screening")
        rules = agent_gateway.invoke(token, "policy.read")
        return screen(report, rules)

    def compliance_verdict(report, violations):
        token = agent_identity.issue_token("pii_compliance")

        def gateway_redact(text):
            return agent_gateway.invoke(token, "pii.redact", text)

        return compliance_decide(report, violations, redactor=gateway_redact)

    agent_registry.register_capability(
        "screening.check_policy", owner="screening", scope="invoke:screening",
        handler=screening_check, kind="agent_skill",
    )
    agent_registry.register_capability(
        "pii_compliance.decide", owner="pii_compliance", scope="invoke:pii_compliance",
        handler=compliance_verdict, kind="agent_skill",
    )
    agent_registry.register_capability(
        "policy.read", owner="screening", scope="policy:read", handler=read_policy, kind="tool",
    )
    agent_registry.register_capability(
        "policy.write", owner="screening", scope="policy:write", handler=write_policy, kind="tool",
    )
    agent_registry.register_capability(
        "pii.redact", owner="pii_compliance", scope="pii:redact", handler=redact, kind="tool",
    )

    # --- the payout pipeline ----------------------------------------------------
    def draft_payout(report):
        return payouts.draft(report)

    def settle_payout(payout_id):
        # The reimbursement agent reaches the ledger as itself, with its own scope —
        # the orchestrator never holds payout:execute, so it cannot pay anyone directly.
        token = agent_identity.issue_token("reimbursement")
        return agent_gateway.invoke(token, "payout.execute", payout_id)

    agent_registry.register_capability(
        "reimbursement.draft", owner="reimbursement", scope="invoke:reimbursement",
        handler=draft_payout, kind="agent_skill",
    )
    agent_registry.register_capability(
        "reimbursement.settle", owner="reimbursement", scope="invoke:reimbursement",
        handler=settle_payout, kind="agent_skill",
        # Read from the ledger, not from the caller: see payouts.py.
        requires_approval=payouts.needs_authorization,
    )
    agent_registry.register_capability(
        "payout.execute", owner="reimbursement", scope="payout:execute",
        handler=payouts.execute, kind="tool",
    )


def review(report):
    """What the Orchestrator does for one report: two gateway calls, in order. Returns
    (violations, result) so the caller can time and trace each step separately.
    """
    token = agent_identity.issue_token("orchestrator")
    violations = agent_gateway.invoke(token, "screening.check_policy", report)
    result = agent_gateway.invoke(token, "pii_compliance.decide", report, violations)
    return violations, result
