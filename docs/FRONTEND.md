# Running the radar without Google Cloud

For Sohan, or anyone with no GCP project, no credits, and no intention of getting
either. **You do not need Google Cloud to work on this frontend.** Verified on a
clean machine with no venv and no `pip install`.

---

## The two-minute version

Two terminals:

```bash
python3 backend/devtools/local_server.py
```

```bash
cd frontend && npm install && npm run dev
```

Open `http://localhost:5173`, click **Live (/events)**. Reports start arriving.

That is the whole setup. No `gcloud`, no `.env`, no credentials, no cost.

---

## Why that works

`backend/devtools/` is a complete reference implementation of the backend with **zero
third-party dependencies** — it runs on the system `python3`, no virtualenv. Confirmed:

- `rules_loader.py` hand-parses `policies/rules.yaml` rather than importing PyYAML.
- `pii_scan.py` is a regex stand-in for Model Armor and Cloud DLP.
- `agent_gateway.py` is an in-process allowlist stand-in for Agent Identity.

It serves **the identical `/events` contract** on the identical port and paths as the
real fleet. Switching between them is stopping one process and starting the other —
the frontend needs no change and cannot tell the difference, which is the whole point
of locking the trace contract on day one.

```bash
python3 backend/devtools/run_eval.py     # 13/13, also zero-dependency
```

### Three modes, in order of setup cost

| Mode | Needs | Use it for |
| :--- | :--- | :--- |
| **Replay (mock)** — the toggle in the UI | nothing at all, not even the backend | pure UI work: layout, animation, styling. Deterministic, instant, replays on demand. |
| **`devtools/local_server.py`** | `python3` | anything touching the SSE client, reconnects, span ordering, the audit drawer. Real streaming, real verdicts from the real rule file. |
| **`fleet/server.py`** | GCP project + credits | only when you specifically need real Model Armor verdicts or real DLP redaction counts on screen. |

For frontend work, mode 2 is the right default. It exercises everything mode 3 does
except which service computed the verdict.

---

## Pointing at a different backend

The URL is configurable — `frontend/src/lib/config.js` reads `VITE_BACKEND_URL`:

```bash
# frontend/.env.local  (gitignored)
VITE_BACKEND_URL=https://whatever-backend.example.com
```

Defaults to `http://localhost:8000`. Leave it unset for local work. This is how the
radar points at a deployed backend later without editing source.

---

## What differs between the stand-in and the real fleet

Worth knowing so a difference doesn't read as a bug you introduced.

| | `devtools/local_server.py` | `fleet/server.py` |
| :--- | :--- | :--- |
| Span timing | `time.sleep(0.25)` per step, so nodes visibly dwell | real durations — screening is sub-millisecond, so its node flashes rather than glows |
| Cadence | ~2s between reports | 6s between reports |
| `armor_verdict` | regex match on injection phrasing | real Model Armor: `PROMPT_INJECTION_BLOCKED (pi_and_jailbreak)` |
| `dlp_redactions` | regex count | real Cloud DLP `redaction_count` |
| Extra spans | none | ADK also emits `call_llm` and `generate_content` — the radar ignores span names it has no node for, by design |
| Approve/deny | `GET` or `POST /approve/:id` | same, both verbs accepted |

The screening node flashing rather than glowing under the real fleet is **real
behaviour, not a rendering bug** — the deterministic policy check genuinely takes
under a millisecond. If that reads badly on camera, the fix is a minimum visual dwell
time in the radar, not a `sleep()` in the backend.

---

## Known frontend issues worth a look

Found while cutting the radar over to the real fleet:

1. **No error boundary.** A malformed span used to blank the entire audit drawer —
   the whole panel went white through React's error boundary, mid-demo. The specific
   cause is fixed on both sides, but nothing stops the next one. A boundary around
   `<AuditDrawer>` that renders "couldn't render this span" instead of nothing would
   be cheap insurance.
2. **`connected` flickers.** `source.onerror` sets `connected` false on every
   transient retry, so the header flips to disconnected during normal reconnects.
   EventSource is retrying on its own; the UI shouldn't announce a failure until a
   retry has actually failed for a while.
3. **The audit trail grows unbounded.** `completedSpans` only ever appends. A demo
   window is fine; an hour is not.
4. **Span-start events carry no attributes.** By design — attributes are only known at
   span end — but it means a node pulses before there is anything to show for it.
   Worth checking the drawer handles an in-flight report gracefully.
