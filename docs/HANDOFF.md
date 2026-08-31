# Handoff — state as of 2026-08-29

The radar now renders the deployed agents, the trace is an enforcement point, and
four reproduced vulnerabilities are closed and redeployed. **Deadline: 2026-08-31, 5:00 PM PT — treat 3 PM as the
real cutoff.**

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
| **Deployed fleet** | **reasoning engine `4324482036380205056`** |
| Security SA | `fleet-security@nice-hangar-506120-t5.iam.gserviceaccount.com` |
| Model | `gemini-3.5-flash`, served from **`global`**, not `us-central1` |

Superseded engines, all earlier deploys of the same fleet. Idle engines are unbilled,
but delete them before demo day so nobody queries the wrong one — and note that two of
them are *useful* until then:

| Engine | Why it exists |
| :--- | :--- |
| `586529530034782208` | the engine the claim vulnerability was found on. `eval_claims --deployed` still fails against it, correctly. Keep until the video is cut — it is the before half of before/after. |
| `138949132692750336` | failed `verify_deployed` because its instruction said to scan fields *joined*. Delete. |
| `3279963582179049472`, `1114576586343972864`, `5958197985580941312` | older still. Delete. |

---

## What is now VERIFIED on the deployed engine

All run against engine `4324482036380205056`, queried via `async_stream_query`.
Reproduce with `python -m fleet.verify_deployed -k 3`:

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

## Closed this session

- **Radar cutover done.** `python -m fleet.server` drives the radar end to end:
  real Model Armor blocks (red intercept + banner), real DLP redaction counts in the
  drawer, real park → Approve → resume. No frontend change was needed.
- **`python -m fleet.verify_deployed`** — one command, three assertions against the
  *deployed* engine, asserting on what Model Armor and Cloud DLP returned rather than
  on what the agent wrote. Currently 3/3.
- **`docs/architecture.png`** — the required Devpost architecture diagram. Source is
  `docs/architecture.svg`; re-render with
  `rsvg-convert -w 2100 -f png -o docs/architecture.png docs/architecture.svg`.
- **README de-staled.** The old top block still said "not built yet: every Google
  Cloud component", four days after it was built.

Three cutover bugs found and fixed, all invisible to the local eval:

1. `fleet.agent` was set *after* `start_as_current_span`, so every `span_start`
   streamed as `orchestrator` — the screening and PII nodes never pulsed and no edge
   ever animated. Attributes now go in at creation.
2. `violations` shipped as `json.dumps(...)` while the trace contract types it as an
   array; `violations.join is not a function` blanked the entire audit drawer through
   React's error boundary, on the one report that *has* violations. Now a real
   sequence, with the drawer normalising either shape.
3. A radar disconnecting mid-SSE printed a full `ConnectionResetError` traceback,
   which on a demo screen reads as the backend crashing. Swallowed in `Server.handle_error`.

## Submission compliance

`docs/SUBMISSION.md` is the checklist, read against the posted Official Rules. Three
things in there that were not obvious from the summary page:

- **The Cloud-service requirement is fine.** The rules say "such as Cloud Run, Cloud
  SQL, ..." — non-exhaustive, so Agent Runtime / Cloud Storage / Cloud Trace qualify.
  Only the Devpost form's checkbox list is narrow. Do not panic-deploy to Cloud Run.
- **The video must show "unedited, live execution."** Beats 3 and 4 are unbroken
  takes. Earlier demo guidance said to cut unwanted fixtures out; that was wrong and
  `docs/DEMO.md` is corrected.
- **The project must stay testable until Oct 1**, not Aug 31 — judging runs a month.
  Idle engines are free; the six-second review loop is not.

## Current state, verified today

```
run_eval.py                      13/13   no GCP, no cost
eval_claims                      48/48   claims, invariants, cross-product, parity
eval_claims --deployed           50/50   the attack, through the real agents
verify_deployed -k 2              3/3    pass^2 on the deployed engine
```

Both server modes work and emit the same span contract:

```
python -m fleet.server                       deterministic — real Armor + DLP, no LLM
FLEET_LIVE_AGENT=1 python -m fleet.server    the deployed agents, 9 spans a report
```

## Remaining work, in order

1. **Record the ~4-minute video.** `docs/DEMO.md` is re-timed for live-agent mode:
   two reports, one unbroken take, 534 words of narration ≈ 3:41. The rules score
   "unedited, live execution", so a bad take is reshot whole, never repaired.
2. **Delete the superseded engines** — but keep `586529530034782208` until the video
   is cut, since it is the *before* in before/after.
3. **Hosted project URL** for the Devpost field. `npm run build` plus a static host is
   the cheap path; `VITE_BACKEND_URL` already makes the backend configurable.
4. **Share the private repo** with `testing@devpost.com` and `cloudhackathons@google.com`,
   then check the link in an incognito window.
5. **Bonus points** — a public write-up and a `#AllThingsAgenticHackathon` post is 0.4
   on a 5-point base for under two hours. `docs/EVALUATION.md` is most of the post.
6. **Submit by 3 PM PT Aug 31**, then stop touching the repo until winners are
   announced. Judging runs to **Oct 1** and the project must stay testable that whole
   time — idle engines are free, the review loops are not.

Explicitly deferred, with README honesty notes in place: per-agent identity split
(one engine/one identity today), manual `register.py` A2A registration
(auto-registration already satisfied the catalog requirement).

---

## Traps paid in earlier sessions (also in README engineering notes)

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

## Traps paid this session (radar cutover)

- Set span attributes at span *creation*, not after — `RadarSpanProcessor` flattens
  `on_start` too, which is the whole point of the pulse.
- OTel attributes hold sequences; `json.dumps`-ing a list breaks the trace contract
  and crashes the drawer.
- Cloud Trace ingestion lags by minutes, and `cloudtrace.v1 traces.list` lags further.
  An empty trace list thirty seconds after a run is not proof the exporter is broken.
- The deployed engine is queried on `:streamQuery` with
  `{"class_method": "async_stream_query", "input": {"user_id", "message"}}`;
  `agent_engines.get()` needs the **full** resource name or it 404s on an HTML page.
- The pause is reported as `long_running_tool_ids` — call *ids*, not names. Resolve
  them through the `function_call` parts in the same run or the proof reads as a
  meaningless hex string.

## Traps paid this session (security hardening)

- **Widening a guardrail's input can weaken it.** Scanning `description +
  receipt_ocr_text` joined made an injection that was blocked when scanned alone come
  back *clean* — extra benign context dilutes the classifier below its confidence
  threshold. Scan per field. This bit twice: once in the code, then again in the
  agent's *instruction*, where it took a failed `verify_deployed` to catch.
- **Model Armor's SDP filter nests `match_state` under `inspect_result`.** Every other
  filter carries it directly. Reading it directly returns None, the overall
  `filter_match_state` still says MATCH_FOUND, and a credit card number gets reported
  as a prompt injection.
- **An attested lookup is only as good as its key.** `records.attested(report_id)`
  trusted a submitter-supplied id, so quoting another report's id inherited its
  receipt. Bind the id to something the record can confirm.
- **A green eval over a stand-in converts unknown into believed-safe.** `run_eval.py`
  tests `devtools/`, not `fleet/`. There is now a parity gate; there was not, and the
  two had already drifted.
- **Instructions are not controls.** The screening agent's prompt said "do not infer a
  receipt exists". It inferred one, three runs out of three.

## Cost — measured, not estimated

**~$4 of the $100 guard consumed across the whole project as of Aug 30**, covering
roughly a hundred deployed-agent runs, three Agent Runtime deploys, and several
hundred Model Armor and Cloud DLP calls. The Console shows net charges at $0.00
because credits absorb it.

That works out to roughly **$0.02–0.04 per agent run**, which makes the practical
numbers:

| Activity | Rough cost |
| :--- | :--- |
| One `verify_deployed -k 3` | under $0.50 |
| One full rehearsal take (2 reports) | pennies |
| Idle deployed engines | free — storage only |
| `FLEET_LIVE_AGENT=1` review loop | **~$4/hour** — 2 reports every 50s, forever |
| Deterministic review loop | far less — no Gemini, but 3 Model Armor calls + DLP per report every 6s |

**Rehearse as many takes as you want.** At pennies each there is no reason to record
a compromised take rather than reshoot it.

**The one real risk is leaving a review loop running unattended.** Live-agent mode
overnight is roughly $50 — it would not exhaust the budget, but it would spend half of
it on nobody watching. Stop the server after every take.

The project must stay testable until judging ends **Oct 1**. That is nearly free: idle
reasoning engines are unbilled, so leaving the deployed fleet up costs storage only.
Do not leave a server loop running to "keep it warm" — the engine does not need it.
