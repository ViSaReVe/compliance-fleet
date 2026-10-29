"""Checks for the Agent Registry / Identity / Gateway stand-ins. Zero GCP calls.

Run: python backend/devtools/run_security_checks.py

Two kinds of check, and both matter:
  * attacks are refused, each for the *specific* reason it should be (a denial for the
    wrong reason means a different check caught it, and the intended one is untested)
  * the guarded path still gives the right answer — routing every call through the
    gateway must not change a single verdict against evals/eval_set.json
"""

import json
import os
import sys

import agent_gateway
import agent_identity
import agent_registry
import agents
import security_demos
from decision import decide
from rules_loader import load_rules

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RULES_PATH = os.path.join(REPO_ROOT, "backend", "policies", "rules.yaml")
EVAL_SET_PATH = os.path.join(REPO_ROOT, "evals", "eval_set.json")

failures = 0


def check(name, ok, detail=""):
    global failures
    if ok:
        print(f"PASS  {name}")
    else:
        failures += 1
        print(f"FAIL  {name}" + (f"  — {detail}" if detail else ""))


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    agents.bootstrap(RULES_PATH)

    # --- registry -------------------------------------------------------------
    names = {a["name"] for a in agent_registry.list_agents()}
    check(
        "registry lists all four agents",
        names == {"orchestrator", "screening", "pii_compliance", "reimbursement"},
        str(names),
    )
    check(
        "capability resolves to its owning agent, not a hardcoded function",
        agent_registry.resolve("screening.check_policy")["owner"] == "screening",
    )
    check(
        "agent cards list their skills with the scope each needs",
        {"id": "screening.check_policy", "scope": "invoke:screening"}
        in agent_registry.find_agent("screening")["skills"],
    )
    try:
        agent_registry.resolve("payments.release")
        check("unregistered capability does not resolve", False)
    except LookupError:
        check("unregistered capability does not resolve", True)
    check(
        "catalog view never leaks handlers",
        all("handler" not in c for c in agent_registry.list_capabilities()),
    )

    # --- identity -------------------------------------------------------------
    token = agent_identity.issue_token("screening")
    claims = agent_identity.verify_token(token)
    check("token carries a spiffe id", claims["sub"] == "spiffe://compliance-fleet.local/agent/screening", claims["sub"])
    check("screening holds only policy:read", claims["scopes"] == ["policy:read"], str(claims["scopes"]))
    check(
        "no agent holds policy:write",
        all("policy:write" not in scopes for scopes in agent_identity.GRANTS.values()),
    )
    try:
        agent_identity.issue_token("rogue_agent")
        check("no identity is provisioned for an unknown agent", False)
    except agent_identity.IdentityError as err:
        check("no identity is provisioned for an unknown agent", err.reason == "UNKNOWN_AGENT", err.reason)

    # --- attacks are refused, for the right reason ----------------------------
    for scenario in security_demos.SCENARIOS:
        denied = security_demos.attempt(scenario)
        check(
            f"{scenario['expected_reason']:<19} {scenario['claim']}",
            denied is not None and denied.reason == scenario["expected_reason"],
            "gateway let it through" if denied is None else f"refused for {denied.reason}",
        )

    # --- every decision is audited, denials included --------------------------
    log = agent_gateway.audit_log()
    check("audit log recorded the denials", sum(1 for d in log if not d["allowed"]) >= len(security_demos.SCENARIOS))
    check("audit log never records a secret", all("token" not in d and "scopes" not in d for d in log))

    # --- the guarded path gives the same answers as the unguarded one ---------
    rules = load_rules(RULES_PATH)
    cases = load_json(EVAL_SET_PATH)["cases"]
    mismatched = []
    for case in cases:
        report = load_json(os.path.join(REPO_ROOT, case["fixture"]))
        violations, guarded = agents.review(report)
        direct = decide(report, rules)
        if guarded != direct or sorted(violations) != sorted(direct["violations"]):
            mismatched.append(case["case_id"])
    check(
        f"gateway-routed verdicts match decide() on all {len(cases)} eval cases",
        not mismatched,
        f"differ: {mismatched}",
    )

    allowed = [d for d in agent_gateway.audit_log() if d["allowed"] and d["capability"] in ("policy.read", "pii.redact")]
    check(
        "agents reached policy and redaction only through the gateway",
        len(allowed) >= len(cases),
        f"{len(allowed)} tool calls audited for {len(cases)} reports",
    )

    print(f"\n{'all checks passed' if not failures else str(failures) + ' check(s) failed'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
