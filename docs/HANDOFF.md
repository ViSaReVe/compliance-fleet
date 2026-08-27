# Handoff — state as of 2026-08-27 (evening)

Second session closed out the deployed-security blockers. **Deadline: 2026-08-31,
5:00 PM PT — treat 3 PM as the real cutoff.**

New session: read this, then `README.md` (*Current state*, *Engineering notes*).
The GEAP surface is verified and written down; do not re-research it.

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
| **Deployed fleet** | **reasoning engine `586529530034782208`** |
| Security SA | `fleet-security@nice-hangar-506120-t5.iam.gserviceaccount.com` |
| Model | `gemini-3.5-flash`, served from **`global`**, not `us-central1` |

Stale engines `3279963582179049472`, `1114576586343972864`, `5958197985580941312`
are earlier deploys of the same fleet — idle engines are unbilled, but delete them
before demo day so nobody queries the wrong one.

---

## What is now VERIFIED on the deployed engine

All three run against engine `586529530034782208`, queried via `async_stream_query`:

- **Model Armor works deployed.** Injection text returns
  `PROMPT_INJECTION_BLOCKED (pi_and_jailbreak)`. The 401 from the first session is
  root-caused and fixed — it was never IAM (401 ≠ 403): Agent Identity's default
  Context-Aware Access policy binds tokens to the agent's mTLS cert, and both Model
  Armor's rep endpoint and `iamcredentials.generateAccessToken` reject bound tokens.
  Fix = security tools impersonate the `fleet-security` SA + deploy sets
  `GOOGLE_API_PREVENT_AGENT_TOKEN_SHARING_FOR_GCP_SERVICES=False`. Details in
  README engineering notes.
- **Cloud DLP works deployed.** `redaction_count: 3` on a card+email fixture. Needed
  `FLEET_PROJECT_ID` because the runtime injects `GOOGLE_CLOUD_PROJECT` as the
  project *number*, which DLP rejects.
- **Pause/resume works deployed.** $6,200 no-preapproval report → compliance agent
  calls `request_manager_approval` → run parks on an `adk_request_confirmation`
  long-running call → resume with a `FunctionResponse` on the same session id →
  final verdict. Same proof also passes locally via `InMemoryRunner`.
  Resume re-runs the sequence from screening before the parked tool resolves —
  expected, not a bug.

Local eval remains 13/13, now exercising the impersonated-SA path end to end
(`FLEET_SECURITY_SA` is set in `backend/.env` by bootstrap).

---

## Remaining work, in order

1. **Radar cutover** — stop `devtools/local_server.py`, start
   `python -m fleet.server` (same port/paths), confirm radar renders real spans.
2. **Demo script + 4-minute video.** Demo scenarios table in README is the outline.
   Scenario 5 (escalation) can now be shown against the deployed engine, or via
   `fleet/server.py`'s park/approve flow on the radar.
3. **README from a clean clone** — `bootstrap.sh` now also creates the
   `fleet-security` SA and grants; verify the doc path once on a fresh checkout.
4. **Delete stale engines** (three ids above).
5. **Submit by 3 PM PT Aug 31.**

Explicitly deferred, with README honesty notes in place: per-agent identity split
(one engine/one identity today), manual `register.py` A2A registration
(auto-registration already satisfied the catalog requirement).

---

## Traps paid for this session (also in README engineering notes)

- 401 vs 403: bound-token rejection reads like missing IAM; it is not.
- Global Model Armor templates are unavailable on this project (permission denied
  even as owner) — the regional rep endpoint is the only path, hence the SA hop.
- Runtime `GOOGLE_CLOUD_PROJECT` = project number; DLP wants the id.
- `adk_request_confirmation` is what actually parks; answer it with
  `{"confirmed": true}` — or answer the original tool call, both resume.
- Keep the `agentplatform.Client` object referenced while streaming; letting it be
  garbage-collected closes its aiohttp session mid-stream (`AssertionError:
  self._connector is not None`).
- usc.edu org sessions force periodic `gcloud auth login` reauth; bootstrap detects
  the stale session poorly (it checks the account list, not token validity).

## Cost

Idle engines unbilled; active processing per vCPU-hour. `fleet/server.py`'s
`review_loop` reviews a fixture every six seconds forever — fine for a demo window,
do not leave it running unattended.
