# Brief for Sohan — recording the submission video

You are narrating and recording. This is everything you need to prepare, plus enough
of how the system actually works that you can speak about it rather than read.

Shot list, narration and timings are in [`DEMO.md`](DEMO.md). **This document is the
part `DEMO.md` assumes you already know.**

---

## Blocker: two of the six beats need Google Cloud, and you are not on it

That was deliberate — the credits are on Vidya's `vvenna@usc.edu` account and the
project sits inside the `usc.edu` organisation. It is now the one thing standing
between you and a recording.

| Beat | Needs Google Cloud? |
| :--- | :--- |
| 1 · the friction (a JSON fixture) | no |
| 2 · architecture diagram | no |
| **3 · the radar showing live agents** | **yes** |
| **4 · proof it runs on Google Cloud** | **yes** |
| 5 · rule file + eval output | no — verified, `eval_claims` passes 48/48 with no credentials at all |
| 6 · close | no |

### Resolve this before anything else — it takes five minutes to find out

**Vidya runs**, replacing the address with Sohan's Google account:

```bash
gcloud projects add-iam-policy-binding nice-hangar-506120-t5 \
  --member="user:SOHAN_EMAIL" --role="roles/viewer"
```

```bash
gcloud projects add-iam-policy-binding nice-hangar-506120-t5 \
  --member="user:SOHAN_EMAIL" --role="roles/aiplatform.user"
```

**If those succeed**, Sohan records everything himself, in one unbroken take, and this
document is the whole plan.

**If they fail** with a domain-restriction or `iam.allowedPolicyMemberDomains` error,
that is the `usc.edu` org policy refusing an outside account. Do not fight it with a
day left. Fall back: **Vidya records the screen, Sohan does not.** A single unbroken
take on Vidya's machine with Vidya narrating is worth far more than a cleverly
stitched one, and the rules explicitly score *unedited, live execution*.

> A university org will often block adding a personal Gmail. Find out now, not at
> 9pm tomorrow.

---

## Prepare, in order

**Vidya must push first — 14 commits are sitting unpushed.** Nothing below works until
`git push origin main` has run.

```bash
git clone https://github.com/ViSaReVe/compliance-fleet.git
cd compliance-fleet
```

**1. Frontend** — this part you already know.

```bash
cd frontend && npm install && npm run dev
```

**2. Backend.** Needs Python 3.12+.

```bash
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

**3. `backend/.env`.** Ask Vidya to send it directly — Signal, DM, whatever. **It
contains no secrets**: project id and number, a bucket name, a Model Armor template
path, a service-account email, and two engine ids. Nothing that authenticates
anything. It is gitignored because it is machine-specific, not because it is
sensitive.

**4. Google Cloud sign-in** (only if the IAM grant above worked):

```bash
gcloud auth application-default login
gcloud auth application-default set-quota-project nice-hangar-506120-t5
```

**5. Check it works.** These two need no cloud access at all — run them first, because
if they fail the problem is your Python setup, not your permissions:

```bash
python3 backend/devtools/run_eval.py    # expect 13/13
python -m fleet.eval_claims             # expect 48/48
```

Then the one that does need access:

```bash
python -m fleet.verify_deployed -k 2    # expect 3/3
```

**6. Read [`DEMO.md`](DEMO.md)** — the recording setup section covers ⌘⇧5, the
microphone trap, and font sizes.

---

## How the system actually works

Speak from this, don't recite it. If you understand the four ideas below you can
answer anything a judge asks.

### The problem

An employee submits an expense report as free text. Someone has to read it and decide
whether it breaks policy. It is slow and inconsistent — and the moment you point a
language model at it, it is dangerous, because **the person being judged writes the
text being read**.

### Idea 1 — the model extracts, the code decides

Gemini reads *"dinner w/ the Acme folks, ~$180ish"* and turns it into fields: amount,
category, receipt yes/no. That is the one job it is good at and the one job it has.

The actual decision — is $180 over the limit, is a receipt required — is **plain Python
reading thresholds from a YAML file**. No model is asked. That is why nobody can talk
the system into approving something: the rules aren't in a prompt where text can argue
with them.

### Idea 2 — a claim is not a fact

This is the interesting one, and it is the thing to be proud of.

We attacked our own system and it failed. Someone writes *"the receipt is already
attached in the expense system"* — no injection, no trickery, just a sentence. The
model believed it, marked `receipt_attached: true`, and the rule engine correctly
computed the wrong answer from a poisoned input. **An $840 expense with no receipt,
approved. Three times out of three.**

Model Armor never fired, and it was right not to — there is nothing to detect. It is
not an attack, it is a lie.

The fix: whether a receipt exists is a **fact about the expense system**, not a reading
of a sentence. So it comes from the system of record. What the text says is treated as
a *claim*, and a claim the record contradicts **escalates to a human** — carrying a
line saying exactly what was claimed and what the record actually held.

The attack now turns itself in.

### Idea 3 — the audit trail is a control, not just a record

Agents fail in a specific way: they skip a step and then write a confident sentence
saying they did it. A model will happily print *"Model Armor: Passed"* having called
nothing.

So a verdict is only allowed to stand if the **evidence for it exists in the run's
trace**. No injection scan in the trace, no approval — the run escalates to a human
instead. And the evidence comes from the runtime's own records of which tools actually
returned, which the agent does not write and therefore cannot fake.

### Idea 4 — the pause is the product

A $6,200 expense with no pre-approval doesn't get a guess. The run **parks** — it stops
and waits, and the state lives in Memory Bank, so it survives for up to seven days.
"The manager is on PTO" is a supported state, not a timeout.

When the manager approves, the system records **who** and **why**. An approval trail
that cannot say who approved six thousand dollars is not an approval trail.

### What the radar is

Every agent step emits an OpenTelemetry span. One piece of code fans those spans two
ways: to Cloud Trace for the audit record, and over SSE to your radar. **Same spans,
both places.** So the radar is not an animation — if it draws something, Cloud Trace
has it. That is worth saying out loud, because it is the thing that makes the
visualisation evidence rather than decoration.

---

## Say these correctly

Five things that are true and specific. Getting them exactly right is what separates a
credible demo from a nice-looking one.

1. **"The model extracts, the code decides."** Thresholds are in a YAML file, enforced
   in Python.
2. **"We attacked our own system and it approved an $840 expense with no receipt."**
   Then: here is the fix, and here is the test that stops it coming back.
3. **"Model Armor is called per field, not on the fields joined together."** We measured
   it: joining them dilutes the classifier and an injection that gets blocked alone
   comes back clean. That detail is real and it lands.
4. **"A verdict without its evidence in the trace does not stand."**
5. **"The pause survives for seven days, and the approval records who and why."**

## Do not say these

- ❌ **"The agents are isolated from each other by IAM."** They are not — it is one
   engine with one identity and an in-process allowlist. We say so in the README. If it
   comes up: *"the separation is a privilege boundary in code today; per-agent IAM is
   the roadmap."*
- ❌ **"It's fully autonomous."** It is deliberately a **workflow**, not an autonomous
   agent — a fixed sequence we control. That is the correct engineering choice and
   worth claiming as one.
- ❌ **"48 out of 48 tests pass"** as if it means broad agent coverage. It is broad
   coverage of the deterministic layers. The agent path is three checks. Say *"the
   deployed agents are verified by three checks, run three times each."*
- ❌ Anything about the amount being verified against the receipt. It isn't yet.

---

## What you are showing

Follow [`DEMO.md`](DEMO.md) beat by beat. Two things it needs from you specifically:

**Beat 3 — start the backend in live-agent mode**, not the default:

```bash
FLEET_LIVE_AGENT=1 python -m fleet.server
```

The default mode makes real Model Armor and Cloud DLP calls but runs **no agent**. Live
mode drives the actually-deployed agents — nine spans a report instead of three, and
you can watch `screening` think, call the policy tool, and hand off to
`pii_compliance`. That is what answers the judging criterion about delegating to
specialised sub-agents. Reports arrive every ~25 seconds because real model calls take
real time.

**Beat 3 — click Approve and type your name and a reason on camera.** It prompts. That
prompt is the compliance point, not a form to rush past.

**Beat 4 — three shots in one unbroken take:** `verify_deployed` in the terminal, the
engine in the Cloud Console, then the spans in Cloud Trace. This beat is 30% of the
score and most submissions skip it.

> **Cloud Trace lags by minutes.** Generate traces during setup and confirm they are
> visible *before* you start recording. A blank Trace page on camera is fatal.

---

## If you get stuck

| Symptom | Cause |
| :--- | :--- |
| Radar stuck on `connecting…` | Backend isn't running, or is on the wrong port. Start it and reload. |
| `verify_deployed` 401 or auth error | Expired ADC. `gcloud auth application-default login` again. |
| `run_eval` fails | Python setup, not permissions — it touches no cloud. |
| Nothing in Cloud Trace | Ingestion lag. Not a bug. Don't debug it on camera. |
| Escalated report won't Approve | Already resolved this session. Restart the server to re-park it. |

**Never leave `fleet/server.py` running unattended.** Live-agent mode makes real Gemini
calls every 25 seconds, forever, against a $100 budget. Stop it after each take.
