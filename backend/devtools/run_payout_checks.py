"""Checks for the payout pipeline, the human-approval gate, and agent availability.
Zero GCP calls.

Run: python backend/devtools/run_payout_checks.py

The cases that matter most are the ones that try to get money out without a person:
lie about the amount, replay a grant, reuse one for a different payout, forge one,
pass one off as an access token, call the ledger directly. Each must be refused for
its *specific* reason. The replay cases matter as much as the attacks: an event
delivered twice must not pay twice.
"""

import base64
import json
import os
import sys
import time
import types

import agent_gateway
import agent_identity
import agent_registry
import agents
import payouts

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RULES_PATH = os.path.join(REPO_ROOT, "backend", "policies", "rules.yaml")

failures = 0


def check(name, ok, detail=""):
    global failures
    if ok:
        print(f"PASS  {name}")
    else:
        failures += 1
        print(f"FAIL  {name}" + (f"  — {detail}" if detail else ""))


def report(rid, amount):
    return {"report_id": rid, "amount_usd": amount, "submitted_by": "employee_001"}


def reason_of(fn, *a, **kw):
    """Run fn; return the refusal reason, 'PARKED', or None if it went through."""
    try:
        fn(*a, **kw)
    except agent_gateway.GatewayDenied as denied:
        return denied.reason
    except agent_gateway.ApprovalRequired:
        return "PARKED"
    return None


def fresh():
    agents.bootstrap(RULES_PATH)


def draft(rid, amount):
    tok = agent_identity.issue_token("orchestrator")
    return agent_gateway.invoke(tok, "reimbursement.draft", report(rid, amount))


def settle(payout_id, approval=None, token=None):
    tok = token or agent_identity.issue_token("orchestrator")
    return agent_gateway.invoke(tok, "reimbursement.settle", payout_id, approval=approval, subject=payout_id)


def approve(payout_id, who="Sohan", capability="reimbursement.settle", **kw):
    return agent_identity.issue_approval(capability, payout_id, who, **kw)


def load_fixture(rid):
    with open(os.path.join(REPO_ROOT, "backend", "fixtures", "reports", f"{rid}.json"), encoding="utf-8") as f:
        return json.load(f)


def integration():
    """Drive the real orchestrate() / resolve_pending() and read the spans they emit."""
    import local_server as srv

    events = []
    srv.broadcast = lambda name, span: events.append((name, dict(span)))
    srv.time = types.SimpleNamespace(sleep=lambda _s: None, time=time.time)

    def fresh_server():
        fresh()
        events.clear()
        srv.pending_approvals.clear()

    def ended(rid):
        return [sp for name, sp in events if name == "span_end" and sp["report_id"] == rid]

    def attrs(rid, key):
        return [sp["attributes"][key] for sp in ended(rid) if key in sp["attributes"]]

    def root_closed(rid):
        return any(sp["parent_id"] is None and sp["end_ms"] for sp in ended(rid))

    # approved + small: paid straight away, no human, root closed
    fresh_server()
    srv.orchestrate(load_fixture("EXP-2026-0001"))
    check("integration: a small approved expense is drafted then paid", attrs("EXP-2026-0001", "payout_status") == ["paid"])
    check("integration: ...with nothing parked and the trace closed", not srv.pending_approvals and root_closed("EXP-2026-0001"))
    check(
        "integration: the payout agent's spans carry its own identity",
        "spiffe://compliance-fleet.local/agent/reimbursement" in attrs("EXP-2026-0001", "identity"),
    )

    # approved + large: parked for a named human
    fresh_server()
    srv.orchestrate(load_fixture("EXP-2026-0008"))
    check("integration: a large approved expense parks on the payout", srv.pending_approvals.get("EXP-2026-0008", {}).get("kind") == "payout")
    check(
        "integration: ...flagged awaiting authorization, not yet paid",
        attrs("EXP-2026-0008", "awaiting_payout_authorization") == [True] and not attrs("EXP-2026-0008", "payout_status"),
    )
    check("integration: ...with the trace still open", not root_closed("EXP-2026-0008"))
    late = "".join(srv.backlog_frames())
    check(
        "integration: a radar joining late is caught up, including the verdict that was already streamed",
        '"verdict": "approved"' in late and '"awaiting_payout_authorization": true' in late,
    )
    try:
        srv.resolve_pending("EXP-2026-0008", "approved")
        check("integration: authorizing with no name is refused", False)
    except ValueError:
        check("integration: authorizing with no name is refused", True)
    check(
        "integration: ...and that refusal did not consume the pending payout",
        "EXP-2026-0008" in srv.pending_approvals and payouts.get("PAY-EXP-2026-0008")["status"] == payouts.DRAFTED,
    )
    check("integration: a named approver releases it", srv.resolve_pending("EXP-2026-0008", "approved", approver="Sohan", reason="CFO signed off"))
    check(
        "integration: ...paid, attributed, trace closed",
        attrs("EXP-2026-0008", "payout_status") == ["paid"]
        and "Sohan" in attrs("EXP-2026-0008", "approver")
        and root_closed("EXP-2026-0008")
        and not srv.pending_approvals,
    )
    check("integration: once the trace closes there is nothing left to replay", srv.backlog_frames() == [])

    # deny cancels the payout
    fresh_server()
    srv.orchestrate(load_fixture("EXP-2026-0008"))
    srv.resolve_pending("EXP-2026-0008", "denied", approver="Sohan", reason="no budget")
    check(
        "integration: denying cancels the payout",
        attrs("EXP-2026-0008", "payout_status") == ["cancelled"] and payouts.get("PAY-EXP-2026-0008")["status"] == payouts.CANCELLED,
    )

    # escalated expense -> manager approves -> payout parks -> a second human authorizes
    fresh_server()
    srv.orchestrate(load_fixture("EXP-2026-0005"))
    check(
        "integration: an escalated expense parks on the expense first",
        srv.pending_approvals.get("EXP-2026-0005", {}).get("kind") == "expense" and payouts.get("PAY-EXP-2026-0005") is None,
    )
    srv.resolve_pending("EXP-2026-0005", "approved", approver="Maya")
    check(
        "integration: approving it moves on to a payout that parks again",
        srv.pending_approvals.get("EXP-2026-0005", {}).get("kind") == "payout" and not root_closed("EXP-2026-0005"),
    )
    srv.resolve_pending("EXP-2026-0005", "approved", approver="Sohan")
    check(
        "integration: the second approval pays it and closes the trace",
        attrs("EXP-2026-0005", "payout_status") == ["paid"] and root_closed("EXP-2026-0005"),
    )

    # things that must never reach the payout stage
    for rid, why in (("EXP-2026-0004", "blocked"), ("EXP-2026-0002", "flagged")):
        fresh_server()
        srv.orchestrate(load_fixture(rid))
        check(f"integration: a {why} expense is never drafted for payout", payouts.get(f"PAY-{rid}") is None)

    # fail closed when an agent the review needs is unavailable
    for agent in ("screening", "pii_compliance"):
        fresh_server()
        agent_registry.set_health(agent, "unavailable")
        srv.orchestrate(load_fixture("EXP-2026-0001"))
        flagged = [v for vs in attrs("EXP-2026-0001", "violations") for v in vs]
        check(
            f"integration: with {agent} unavailable the report goes to a human, not through",
            srv.pending_approvals.get("EXP-2026-0001", {}).get("kind") == "expense"
            and attrs("EXP-2026-0001", "verdict") == ["escalated"]
            and "FLEET_DEGRADED" in flagged
            and payouts.get("PAY-EXP-2026-0001") is None,
        )


def main():
    # --- planning is guarded by state, so replays are harmless -----------------------
    fresh()
    check("a new approved expense plans a draft", payouts.plan_capability("ExpenseApproved", "R1") == "reimbursement.draft")
    check("an unknown event plans nothing", payouts.plan_capability("Nonsense", "R1") is None)
    check("PayoutDrafted before any draft plans nothing", payouts.plan_capability("PayoutDrafted", "R1") is None)
    draft("R1", 120)
    check("a replayed ExpenseApproved plans nothing once drafted", payouts.plan_capability("ExpenseApproved", "R1") is None)
    check("PayoutDrafted plans a settlement", payouts.plan_capability("PayoutDrafted", "R1") == "reimbursement.settle")
    settle("PAY-R1")
    check("a replayed PayoutDrafted plans nothing once paid", payouts.plan_capability("PayoutDrafted", "R1") is None)

    # --- small payouts need no human; large ones cannot proceed without one ----------
    fresh()
    draft("SMALL", 120)
    check("a payout under the threshold settles without approval", payouts.get("PAY-SMALL") is not None and reason_of(settle, "PAY-SMALL") is None)
    check("...and is marked paid", payouts.get("PAY-SMALL")["status"] == payouts.PAID)

    draft("BIG", 5000)
    check("a payout over the threshold is parked, not paid", reason_of(settle, "PAY-BIG") == "PARKED")
    check("...and stays unpaid", payouts.get("PAY-BIG")["status"] == payouts.DRAFTED)
    ok = reason_of(settle, "PAY-BIG", approval=approve("PAY-BIG"))
    check("a named human's approval releases it", ok is None and payouts.get("PAY-BIG")["status"] == payouts.PAID, str(ok))

    boundary = payouts.AUTHORIZATION_THRESHOLD_USD
    draft("EDGE-AT", boundary)
    draft("EDGE-OVER", boundary + 0.01)
    check("exactly at the threshold needs no human (the cap is exclusive)", reason_of(settle, "PAY-EDGE-AT") is None)
    check("one cent over needs one", reason_of(settle, "PAY-EDGE-OVER") == "PARKED")

    # --- the amount that decides is the ledger's, not the caller's -------------------
    fresh()
    draft("LIE", 9000)
    check(
        "a caller cannot lower the amount to dodge approval (it is not an argument)",
        reason_of(settle, "PAY-LIE") == "PARKED" and payouts.get("PAY-LIE")["amount_usd"] == 9000,
    )

    # --- approvals cannot be forged, repurposed, replayed, or anonymous --------------
    fresh()
    draft("A", 4000)
    draft("B", 4000)
    grant_a = approve("PAY-A")
    check("an approval for payout A is refused on payout B", reason_of(settle, "PAY-B", approval=grant_a) == "APPROVAL_MISMATCH")
    check(
        "an approval for a different capability is refused",
        reason_of(settle, "PAY-B", approval=approve("PAY-B", capability="payout.execute")) == "APPROVAL_MISMATCH",
    )
    body, sig = approve("PAY-B").split(".", 1)
    claims = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    claims["approver"] = "someone else"
    forged = base64.urlsafe_b64encode(json.dumps(claims, separators=(",", ":")).encode()).rstrip(b"=").decode() + "." + sig
    check("an edited approval fails its signature", reason_of(settle, "PAY-B", approval=forged) == "BAD_SIGNATURE")
    check("an expired approval is refused", reason_of(settle, "PAY-B", approval=approve("PAY-B", ttl_s=-5)) == "APPROVAL_EXPIRED")
    check(
        "an access token cannot stand in for an approval",
        reason_of(settle, "PAY-B", approval=agent_identity.issue_token("orchestrator")) == "WRONG_TOKEN_TYPE",
    )
    check(
        "an approval cannot be used as an access token",
        reason_of(settle, "PAY-B", token=approve("PAY-B")) == "WRONG_TOKEN_TYPE",
    )
    try:
        agent_identity.issue_approval("reimbursement.settle", "PAY-B", "  ")
        check("an approval with no name is refused at issue", False)
    except agent_identity.IdentityError as err:
        check("an approval with no name is refused at issue", err.reason == "APPROVER_REQUIRED", err.reason)
    check("nothing above released payout B", payouts.get("PAY-B")["status"] == payouts.DRAFTED)

    check("approval for A releases A", reason_of(settle, "PAY-A", approval=grant_a) is None)
    check("the same approval cannot be spent twice", reason_of(settle, "PAY-A", approval=grant_a) == "APPROVAL_USED")
    again = settle("PAY-A", approval=approve("PAY-A"))
    check("even a fresh approval cannot pay A a second time", again["already_paid"] is True, str(again))

    # --- only the reimbursement agent can reach the ledger ---------------------------
    fresh()
    draft("DIRECT", 50)
    orch = agent_identity.issue_token("orchestrator")
    scr = agent_identity.issue_token("screening")
    check(
        "the orchestrator cannot pay anyone directly",
        reason_of(agent_gateway.invoke, orch, "payout.execute", "PAY-DIRECT") == "MISSING_SCOPE",
    )
    check(
        "screening cannot pay anyone directly",
        reason_of(agent_gateway.invoke, scr, "payout.execute", "PAY-DIRECT") == "MISSING_SCOPE",
    )
    check("no scope is shared between money and review", not (agent_identity.GRANTS["reimbursement"] & agent_identity.GRANTS["orchestrator"]))

    # --- availability fails closed, degraded does not --------------------------------
    fresh()
    agent_registry.set_health("screening", "degraded")
    tok = agent_identity.issue_token("orchestrator")
    check("a degraded agent still takes calls", reason_of(agent_gateway.invoke, tok, "screening.check_policy", report("X", 10)) is None)
    agent_registry.set_health("screening", "unavailable")
    check("an unavailable agent is refused", reason_of(agent_gateway.invoke, tok, "screening.check_policy", report("X", 10)) == "AGENT_UNAVAILABLE")
    agent_registry.set_health("screening", "healthy")
    agent_registry.set_lifecycle("screening", "disabled")
    check("a disabled agent is refused", reason_of(agent_gateway.invoke, tok, "screening.check_policy", report("X", 10)) == "AGENT_UNAVAILABLE")
    agent_registry.set_lifecycle("screening", "active")
    check("restoring it restores service", reason_of(agent_gateway.invoke, tok, "screening.check_policy", report("X", 10)) is None)
    agent_registry.set_health("pii_compliance", "unavailable")
    check(
        "an unavailable owner takes its tools down too",
        reason_of(agent_gateway.invoke, agent_identity.issue_token("pii_compliance"), "pii.redact", "x") == "AGENT_UNAVAILABLE",
    )

    # --- descriptors and the audit trail ----------------------------------------------
    fresh()
    cards = {c["name"]: c for c in agent_registry.list_agents()}
    check("every agent declares a risk level", all(c["risk_level"] in agent_registry.RISK_LEVELS for c in cards.values()))
    check("the agent that moves money is the only CRITICAL one", [n for n, c in cards.items() if c["risk_level"] == "CRITICAL"] == ["reimbursement"])
    check("cards list granted scopes apart from offered skills", cards["screening"]["granted_scopes"] == ["policy:read"] and cards["screening"]["skills"][0]["id"] == "screening.check_policy")
    check("the catalog marks which capabilities need a human", {c["capability"] for c in agent_registry.list_capabilities() if c["human_approval"]} == {"reimbursement.settle"})

    draft("AUD", 3000)
    reason_of(settle, "PAY-AUD")  # parked first, as it would be in real use
    settle("PAY-AUD", approval=approve("PAY-AUD", who="Sohan"))
    log = agent_gateway.audit_log()
    paid = [d for d in log if d["capability"] == "reimbursement.settle" and d["allowed"]]
    check("the audit log records who approved a payout", bool(paid) and paid[-1].get("approver") == "Sohan")
    parked = [d for d in log if d["reason"] == "APPROVAL_REQUIRED" and d["capability"] == "reimbursement.settle"]
    check("the audit log records the attempt that was parked", bool(parked) and not parked[-1]["allowed"])
    check("the audit log holds no tokens or grants", all(not any(k in d for k in ("token", "approval", "jti")) for d in log))

    integration()

    print(f"\n{'all checks passed' if not failures else str(failures) + ' check(s) failed'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
