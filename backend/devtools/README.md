# backend/devtools — local reference pipeline (temporary)

Zero-dependency, zero-GCP-cost implementation of the `/events` SSE contract, built
purely from `backend/fixtures/reports/*.json` and `policies/rules.yaml`. It exists so
the frontend radar and the orchestration/telemetry design can be proven end-to-end
before the real ADK agents exist.

**What's real here:** the rule-matching logic (`rule_engine.py`), the orchestration
sequencing (screening → pii_compliance), and the trace contract emitted over SSE —
all genuinely computed per report, not scripted.

**What's a stand-in, not the real thing:**
- No LLM call extracts fields from free text — fixtures are already structured JSON,
  so extraction is skipped entirely. Real `screening.py` still needs Gemini for that.
- `pii_scan.py` is a regex keyword/pattern match, not Model Armor or Cloud DLP.
- No Memory Bank or Agent Runtime deploy involved. Registry, identity, and gateway are local stand-ins (see below).

## Registry, identity, and gateway (local)

Zero-cost versions of the three GEAP security pieces. Same shape as the managed
services, enforced by plain Python instead of Google Cloud:

| Piece | File | What it does |
| :--- | :--- | :--- |
| Agent Registry | `agent_registry.py` | Catalog of agent cards and capabilities. The Orchestrator asks for `screening.check_policy` by name; it never imports the function. |
| Agent Identity | `agent_identity.py` | A SPIFFE-style id per agent and HMAC-signed, 60 s tokens carrying scopes. `policy:read` is Screening's alone, `pii:redact` is PII/Compliance's alone, `policy:write` is nobody's. |
| Agent Gateway | `agent_gateway.py` | Every call goes through `invoke()`: verify the token, resolve the capability in the registry, check the scope. Each refusal has its own reason, and every decision is audited. |

`agents.py` provisions all three (`bootstrap`) and runs each agent as its own identity.
`security_demos.py` holds eight attacks: wrong scope (two ways), forged token, expired token,
unregistered capability, the Orchestrator paying directly, a replayed approval, and an approval
for one payout presented for another. The server streams one per pass as
a BLOCKED span; `run_security_checks.py` asserts each is refused for the *specific*
reason, and that routing through the gateway changes no verdict on `evals/eval_set.json`.

```bash
python backend/devtools/run_security_checks.py   # 21 checks
python backend/devtools/run_payout_checks.py     # 60 checks
# no GCP, no cost
```

`GET /registry` and `GET /gateway/audit` expose the catalog and the decision log.

**Descriptors.** Agent cards carry `risk_level`, `lifecycle`, `health` and `fallback_agent`, plus
`granted_scopes` kept separate from the skills an agent offers. An unavailable agent is refused
(`AGENT_UNAVAILABLE`) and the orchestrator routes the report to a human instead of guessing.

**Second pipeline: payouts.** An approved expense is paid by a separate `reimbursement` agent
(`payouts.py`, state machine `drafted → paid | cancelled`). Payouts over $500 are parked until a
*named* person authorizes them: the gateway refuses `reimbursement.settle` without a signed,
single-use approval bound to that one payout. Replaying an event cannot pay twice, and the amount
that decides whether a person must approve is read from the ledger, never from the caller. The
radar shows the fourth node, a `payout pending` pill, and an **Authorize** button. A radar that
connects late is caught up on anything parked.

Design notes: [`docs/decisions/`](../../docs/decisions/) and
[`docs/COMPLIANCE-MATRIX.md`](../../docs/COMPLIANCE-MATRIX.md).

**Manual submission.** `POST /submit` takes a JSON expense (amount, category, merchant,
description, receipt/pre-approval flags) and streams its review to the radar like any
fixture. The report id is assigned by the server (`EXP-MANUAL-####`) and a client-supplied
one is ignored — a submitter-chosen id is the spoofing hole `docs/REVIEW.md` reproduces.
Amounts, field lengths and body size are validated. The radar's "Submit an expense" panel
(Live mode only) drives it. `POST /approve/<id>?approver=&reason=` and `/deny/` work here too,
matching the real fleet server, so "who and why" is recorded locally. They are POST-only: a GET
can be fired by a link prefetcher, and approving a payout is a state change. Authorizing a
payout with no name returns 400 and leaves it parked.

**What this is not:** the identity here is a signed token, not an mTLS-bound SPIFFE
certificate, and the gateway is a function, not a managed IAP-enforced service. It
proves the *design* — least scope, lookup by capability, refusal with a reason — not
the Google Cloud deployment of it.

**Run it:**
```bash
python backend/devtools/local_server.py
```
Serves `http://localhost:8000/events` — the exact URL the frontend's Live mode
already expects (`frontend/src/App.jsx` → `EVENTS_URL`).

**When to delete this folder:** once `backend/fleet/server.py` exists and serves the
real thing on the same URL. Nothing in the frontend needs to change when that happens.

**Demo persona views (frontend, Live mode).** A switch above the radar offers Overview,
Employee, Reviewer and Finance ops. It is a *view* switch, **not a sign-in**: the backend has no
notion of who is asking, every endpoint answers every view, and the approver name is typed, not
verified. Employee shows only the ids this browser submitted; Reviewer lists everything parked on
a person, oldest first, with Approve/Authorize/Deny and how many values were redacted; Finance
ops shows `/registry` (risk, health, capabilities) and `/gateway/audit` (an `APPROVAL_REQUIRED`
is shown as *parked*, not refused). Real per-role access would need authenticated identities on
the backend; that is not built.
