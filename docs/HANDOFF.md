# Handoff — state as of 2026-08-27

Written at the end of the first build session so a new session can pick up without
re-deriving anything. **Deadline: 2026-08-31, 5:00 PM PT.**

If you are a new session: read this, then `README.md` (especially *Current state* and
*Engineering notes*). Do not re-research the GEAP surface — it is already verified and
written down.

---

## Identifiers

| Thing | Value |
| :--- | :--- |
| Repo | `github.com/ViSaReVe/compliance-fleet` (private) |
| Collaborator | `Sohan-5` — GitHub only, deliberately not on GCP |
| GCP project | `nice-hangar-506120-t5` (number `28048016313`) |
| Organization | `usc.edu` = `794027733634` |
| Google account | `vvenna@usc.edu` — credits live here, not the personal gmail |
| Billing | `01F4BE-456C5D-7D4754`, budget `hackathon-guard` at $100 |
| Memory Bank | agent engine `6748861195161174016` |
| Deployed fleet | reasoning engine `3279963582179049472` |
| Model | `gemini-3.5-flash`, served from **`global`**, not `us-central1` |

---

## What works

**Locally** (`backend/fleet/`, run from `backend/` with `venv` activated):
- All 13 fixtures produce their expected verdict via `orchestrator.decide()`
- Model Armor blocks prompt injection, passes benign text
- Cloud DLP redacts card / SSN / email / address
- Spans reach Cloud Trace with every `fleet.*` attribute
- `python3 backend/devtools/run_eval.py` → 13/13

**Deployed on Agent Runtime** (engine `3279963582179049472`):
- Gemini extracts structured fields from free-text submissions
- The screening agent calls `check_expense_policy` and returns real violations
- Agent Registry **auto-registered** the engine with its Agent Identity principal,
  framework detected as `google-adk` — no manual registration was needed
- Memory Bank attached

**Frontend** (`frontend/`, Sohan's): radar, sweep, drawer, SSE client, all working
against `backend/devtools/local_server.py`.

---

## What is broken

**The deployed agent's Model Armor call returns 401.**

```
ARMOR_UNAVAILABLE: 401 Request had invalid authentication credentials.
```

`roles/modelarmor.user` and `roles/dlp.user` were granted to the agent principal set
but had not taken effect when the session ended. Unresolved: whether this is IAM
propagation delay, or the custom regional `api_endpoint` in `compliance.py` not
accepting agent-identity credentials.

Two things to try, in order:
1. Re-run the query — it may simply have propagated by now.
2. Drop the `client_options` endpoint override in `compliance._armor()` and let the
   client resolve the endpoint itself.

Note the failure is **fail-closed by design**: the agent reports `blocked` /
`ARMOR_UNAVAILABLE` rather than claiming a pass it did not get. That behaviour is
correct and should not be "fixed" by making it fail open.

---

## What has never been run

- `fleet/register.py` — manual Agent Registry registration. Possibly unnecessary,
  since auto-registration already worked; decide before spending time on it.
- `fleet/approval.py` — the `LongRunningFunctionTool` pause/resume path. Written and
  imports cleanly, never exercised. **This is the Agent Runtime long-running proof and
  it is a scored part of the track.**
- `fleet/server.py` against the real fleet — it serves the same paths and port as the
  devtools stand-in, so cutover should be stop-one-start-the-other.
- Per-agent identities. Right now the whole `SequentialAgent` deploys as one engine
  with one identity. The README claims "Screening Agent cannot reach PII redaction" —
  that is currently only true of `devtools/agent_gateway.py`'s in-process allowlist,
  **not** of real IAM. Either deploy the two sub-agents as separate engines so each
  gets its own identity, or soften the claim. Do not demo it as IAM-enforced until it is.

---

## Priorities for the remaining time

1. **Clear the Model Armor 401** so the deployed path does real security, not narrated
   security. Highest value: it is the difference between the demo being true and not.
2. **Exercise the pause/resume path** — `request_confirmation()` inside the
   `LongRunningFunctionTool`. Scored, and currently unproven.
3. **Cut the radar over** from `devtools/local_server.py` to `fleet/server.py`.
4. **Decide the per-agent identity question** above, honestly.
5. Demo script, README verified from a clean clone, 4-minute video, submit **by 3 PM PT
   on Aug 31**, not 5.

---

## Traps already paid for

Every one of these cost real time this session and is written up in the README's
*Engineering notes*. Do not rediscover them:

- `gemini-3.5-flash` is served from `global`; the deployed runtime needs
  `env_vars={"GOOGLE_CLOUD_LOCATION": "global"}` or it 404s the model
- ...but Model Armor, DLP, Agent Runtime, Memory Bank and Agent Registry are all
  **regional**, hence `config.SERVICE_LOCATION` existing separately from `LOCATION`
- `GOOGLE_CLOUD_PROJECT` is a reserved env var on Agent Runtime and is rejected
- tools are plain functions, so cloudpickle serialises them by module reference —
  `extra_packages=["fleet", "policies"]` is mandatory or the runtime cannot start
- `vertexai.Client` → `agentplatform.Client` (different class, not an alias)
- Memory Bank settings live at `context_spec.memory_bank_config`, not top level
- streaming methods are on `:streamQuery`, not `:query`
- `CloudTraceSpanExporter` is deprecated and silently delivers nothing; use OTLP to
  `telemetry.googleapis.com` with a resource carrying `gcp.project_id`
- `gcloud beta ai reasoning-engines` does not exist — list engines via the SDK
- Cloud DLP never detects `123-45-6789`; use a pattern-valid synthetic SSN
- **Nothing above reproduces locally**, because `orchestrator.decide()` is the
  deterministic path and makes no model call. Always query the deployed engine before
  believing a deploy worked.

---

## Cost

Idle Agent Runtime engines are not billed; you pay per vCPU-hour of active processing.
Stale engines from the debug cycle have been deleted — only the two above remain.

The real risk is `fleet/server.py`'s `review_loop`, which reviews a fixture every six
seconds forever. Do not leave it running unattended.
