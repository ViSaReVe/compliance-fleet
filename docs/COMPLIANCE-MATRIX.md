# Compliance matrix

What this project claims against the Fortified Enterprise Fleet track, and **how well each
claim is supported**. The format is borrowed from the EIR hospital-fleet project, whose
compliance matrix labels every row `VERIFIED` or `CONFIGURED UNVERIFIED` with the evidence next
to it. That is a better habit than a feature list: it makes the gaps as visible as the
strengths, and a reader can stop trusting nothing and start trusting exactly what is checked.

## How to read the Status column

| Status | Meaning |
| :--- | :--- |
| **CHECKED LOCALLY** | A script in this repo asserts it, with no cloud account. Re-run it yourself. |
| **CLAIMED, DEPLOYED** | Stated in `README.md` / `process/HANDOFF.md` as verified against the deployed engine. **Not re-run when this page was written**, because that needs Google Cloud access. Re-run `python -m fleet.verify_deployed -k 3` to confirm. |
| **LOCAL STAND-IN** | Implemented as plain Python with the same shape as the managed service. Proves the *design*, not the Google Cloud deployment. |
| **NOT DONE** | Absent. Listed so nobody has to discover it. |

## Required by the rules

| Requirement | Implementation | Evidence | Status |
| :--- | :--- | :--- | :--- |
| Gemini 3.5+ | `gemini-3.5-flash` via Vertex AI, every agent | `README.md`; visible in the deployed engine's stream | CLAIMED, DEPLOYED |
| Google agent framework | ADK 2.7.1: `LlmAgent`, `SequentialAgent`, `LongRunningFunctionTool` | `backend/fleet/` | CLAIMED, DEPLOYED |
| Google Cloud infrastructure service | Agent Runtime, Cloud Storage (staging), Cloud Trace | `README.md` | CLAIMED, DEPLOYED |

## Track components

| Component | Implementation | Evidence | Status |
| :--- | :--- | :--- | :--- |
| Agent Runtime | Fleet deployed as one reasoning engine | `fleet/deploy.py`; `verify_deployed` | CLAIMED, DEPLOYED |
| Memory Bank | Attached to the engine; parked runs resume on the same session | `fleet/approval.py`; `verify_deployed` | CLAIMED, DEPLOYED |
| Agent Registry | Auto-registered on deploy. Manual `register.py` A2A registration was deferred | `README.md` honesty notes | CLAIMED, DEPLOYED |
| Agent Registry (local) | Agent cards + capabilities; the Orchestrator resolves by name | `backend/devtools/agent_registry.py`; `run_security_checks.py` | CHECKED LOCALLY · LOCAL STAND-IN |
| Agent Identity | One SPIFFE identity for the whole engine | `fleet/deploy.py` | CLAIMED, DEPLOYED |
| Per-agent identity split | Each agent its own engine and identity | — | **NOT DONE** on Google Cloud |
| Per-agent identity (local) | SPIFFE-style id per agent, signed 60 s tokens with scopes | `backend/devtools/agent_identity.py`; `run_security_checks.py` | CHECKED LOCALLY · LOCAL STAND-IN |
| Agent Gateway | Managed gateway with IAP enforcement | — | **NOT DONE** (multi-day: Terraform + Private Service Connect + IAP) |
| Agent Gateway (local) | Token → registry → scope → human-approval check on every call; audit log | `backend/devtools/agent_gateway.py`; `run_security_checks.py`, `run_payout_checks.py` | CHECKED LOCALLY · LOCAL STAND-IN |
| Model Armor | Real tool, per-field scanning | `fleet/compliance.py`; `verify_deployed` | CLAIMED, DEPLOYED |
| Cloud DLP | Real redaction, not narrated | `fleet/compliance.py`; `verify_deployed` | CLAIMED, DEPLOYED |
| Agent Observability | One `SpanProcessor`, two sinks: Cloud Trace and SSE to the radar | `fleet/telemetry.py` | CLAIMED, DEPLOYED |
| Pause / resume | `request_confirmation()` parks a run for a manager | `fleet/approval.py`; `verify_deployed` | CLAIMED, DEPLOYED |

## Behavior claims

| Claim | Evidence | Status |
| :--- | :--- | :--- |
| Thresholds are enforced in code, never in a prompt | `fleet/policy.py`, `policies/rules.yaml`; `run_eval.py` 13/13 | CHECKED LOCALLY |
| A false claim of a receipt/pre-approval escalates instead of approving | `fleet/eval_claims.py` | CHECKED LOCALLY; deployed run CLAIMED |
| Screening cannot reach PII redaction; PII cannot write policy; nobody can write policy | `run_security_checks.py` | CHECKED LOCALLY · LOCAL STAND-IN |
| A forged, expired, or mistyped token, or an unregistered capability, is refused for its specific reason | `run_security_checks.py` | CHECKED LOCALLY · LOCAL STAND-IN |
| An unavailable agent fails closed: the report goes to a human, not through | `run_payout_checks.py` | CHECKED LOCALLY · LOCAL STAND-IN |
| A payout over $500 cannot be made without a named human's approval | `run_payout_checks.py` | CHECKED LOCALLY · LOCAL STAND-IN |
| An approval is bound to one payout, expires, and pays once; an event replayed twice does not pay twice | `run_payout_checks.py` | CHECKED LOCALLY · LOCAL STAND-IN |
| The amount that decides whether a person must approve comes from the ledger, not the caller | `run_payout_checks.py` | CHECKED LOCALLY · LOCAL STAND-IN |
| Report ids are assigned by the system, never accepted from the submitter (manual entry) | `backend/devtools/local_server.py` `/submit` | CHECKED LOCALLY (local pipeline only; the real fleet still takes a submitter-supplied id — see `REVIEW.md`) |
| The radar renders real spans, not an animation | `fleet/telemetry.py` and the radar's SSE client | CLAIMED, DEPLOYED |

## Second pipeline

| Claim | Evidence | Status |
| :--- | :--- | :--- |
| A payout pipeline (draft → settle) runs beside the expense review, sharing registry, identity and gateway | `backend/devtools/payouts.py`, `agents.py` | CHECKED LOCALLY · LOCAL STAND-IN |
| It exists on Google Cloud | — | **NOT DONE**. Local only; synthetic ledger, no money moves |

## Explicit non-claims

- Nothing here is a compliance certification. "Compliance" is the problem domain.
- No real expenses, employees, or payments. Fixtures are synthetic.
- The local identity is an HMAC-signed token, **not** an mTLS-bound SPIFFE certificate; the local gateway is a function, **not** a managed IAP-enforced service. Neither is evidence about the Google Cloud deployment.
- The approver's name is caller-supplied. It is recorded and bound into the approval, but not authenticated.
- A hosted demo existed at one point and was taken down to stop cloud charges; it is not part of this repository.
- The regex PII/injection scanner in `backend/devtools/` is a stand-in, not Model Armor or Cloud DLP.

## Re-running everything that can be checked without a cloud account

```bash
python backend/devtools/run_eval.py              # 13 policy cases
python backend/devtools/run_security_checks.py   # registry, identity, gateway, attacks
python backend/devtools/run_payout_checks.py     # payout pipeline, approvals, fail-closed
```
