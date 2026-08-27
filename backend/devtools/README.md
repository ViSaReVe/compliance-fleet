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
- No Agent Registry, Agent Identity, Memory Bank, or Agent Runtime deploy involved.

**Run it:**
```bash
python backend/devtools/local_server.py
```
Serves `http://localhost:8000/events` — the exact URL the frontend's Live mode
already expects (`frontend/src/App.jsx` → `EVENTS_URL`).

**When to delete this folder:** once `backend/fleet/server.py` exists and serves the
real thing on the same URL. Nothing in the frontend needs to change when that happens.
