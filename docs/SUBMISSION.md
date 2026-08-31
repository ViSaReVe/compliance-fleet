# Submission checklist — read against the official rules

Every line here is checked against the posted Official Rules, not against memory.
Deadline **Aug 31, 2026, 5:00 PM PT**. Treat 3 PM as the cutoff.

---

## Correction to earlier advice

I previously flagged the Google Cloud service requirement as a possible blocker,
because the Devpost form's checkbox list is Cloud Run / Cloud SQL / Firestore / GKE /
Pub/Sub and we use none of them. **The rules are looser than the form.** The actual
wording:

> "AND at least one Google Cloud infrastructure service (**such as** Cloud Run, Cloud
> SQL, Firestore, GKE, Pub/Sub)"

"Such as" is non-exhaustive. Agent Runtime, Cloud Storage and Cloud Trace are Google
Cloud infrastructure services, so **the requirement is satisfied as-is** — and the
track brief itself names Agent Runtime, Memory Bank, Agent Registry and Model Armor
as the expected stack, so ticking none of the five is expected for this track.

The form field is still awkward. Cloud Run remains worth doing, but as *form
convenience plus the hosted URL*, not as a compliance rescue. Don't panic-deploy.

---

## The three mandatory requirements

| Requirement | Status | Evidence |
| :--- | :--- | :--- |
| Gemini 3.5 or newer, via Gemini API or Vertex AI | ✅ | `gemini-3.5-flash` through Vertex AI, every agent. Visible in the deployed engine's own stream: `"model_version": "gemini-3.5-flash"` |
| At least one Google agent framework | ✅ | ADK 2.7.1 — `LlmAgent`, `SequentialAgent`, `LongRunningFunctionTool` |
| At least one Google Cloud infrastructure service | ✅ | Agent Runtime, Cloud Storage (staging bucket), Cloud Trace |

---

## Submission form

| Field | Status | Note |
| :--- | :--- | :--- |
| Category selected | ⬜ | **Fortified Enterprise Fleet.** Easy to skip when rushing — the form starts unselected |
| Text description | ⬜ | Must cover: features & functionality, technologies used, other data sources, **findings and learnings**. The findings section writes itself from [EVALUATION.md](EVALUATION.md) |
| Code repo URL | ⚠️ | Repo is **private** → must share with `testing@devpost.com` **and** `cloudhackathons@google.com`. Then open the link in an incognito window to confirm |
| README spin-up instructions | ✅ | README Setup, steps 1–5, plus [FRONTEND.md](FRONTEND.md) for the no-GCP path |
| Architecture diagram **uploaded** | ✅ file exists, ⬜ upload | `docs/architecture.png`. The form takes pdf/ppt/pptx/png/jpg — it must be attached, not just linked from the README |
| Demo video | ⬜ | ~4 min, **public** on YouTube or Vimeo, English. Script: [DEMO.md](DEMO.md). Upload early — processing takes hours |
| Hosted project URL | **skipped, deliberately** | Left empty. It is optional, and the demo is 30% of the score — spending recording time on infra to fill an optional field is a bad trade the night before. `frontend/` already builds a hostable variant (`VITE_DEMO_ONLY=1 npm run build -- --outDir dist-hosted`, relative asset paths, Live toggle hidden) if there is time after submitting |
| Project start date | ⬜ | Must fall inside Aug 3 – Aug 31, 2026 |
| Google SDK used | ⬜ | Agent Development Kit (ADK) |
| Submitter type + country | ⬜ | Team of individuals · United States |
| Teammates **accepted** | ⚠️ | Sohan must *accept* the invite. An unaccepted invite is the top way someone gets left off a finished submission |

---

## Two rules that cost real money and time if missed

**1. The project must stay live until October 1, 2026.**

> "The Entrant must make the Project available free of charge and without any
> restriction, for testing, evaluation and use by the Sponsor, Administrator and
> Judges **until the Judging Period ends**."

Judging runs Sept 1 – **Oct 1**. So the deployed engine, and any hosted URL, must
survive a month past the deadline — not just demo day. Idle reasoning engines are
unbilled, so the engine itself is nearly free to leave up; a Cloud Run service with
min-instances 0 is likewise ~free. What is *not* free is leaving `fleet/server.py`'s
six-second review loop running: that is a real Model Armor + Cloud DLP call every six
seconds, forever, against the $100 budget guard. **Never leave it running unattended.**

**2. Do not touch anything after you submit.**

Once the Submission Period ends the submission locks, and changing linked materials
can put eligibility at risk. If you want to keep building, fork the repo and work
there — leave the submitted commit untouched.

---

## Scoring, read closely

The rules publish per-track sub-criteria that the summary page does not. These change
what the video should say.

### Innovation & Operational Utility — 40%

> "Is the task complex enough to warrant a multi-agent system? Does the system
> intelligently delegate tasks to specialized sub-agents? **Did they build this for an
> 'Unlikely Hero' outside of standard corporate roles?**"

⚠️ **This is our weakest line.** Expense compliance is about as standard-corporate as
a use case gets. We cannot rewrite the project in two days, and shouldn't — but the
framing is free. The honest version: the unlikely hero here is not the finance team,
it is the **person whose $840 reimbursement is sitting in a queue**, and the reviewer
who has to be the one who says no. Say that out loud in beat 1 rather than pitching
"enterprise compliance automation", which sounds like exactly the standard corporate
role the criterion is steering away from.

### Architectural Discipline & Tech Stack — 30%

> "Is there a **clear, strictly enforced** separation of concerns between agents? Is
> the inter-agent routing logic **failure-tolerant (e.g., how does the system recover
> if a worker agent loops or returns a hallucination)?**"

Two things here, one bad and one very good.

⚠️ **"Strictly enforced" separation — we do not have it.** One engine, one Agent
Identity, an in-process allowlist. Already disclosed in the README, and beat 5 of the
demo names it. Keep naming it. A judge who finds it themselves discounts everything
else; a team that names it is read as trustworthy on the rest.

✅ **"Recover if a worker agent returns a hallucination" — this is now our best
answer, and it is unusually literal.** The screening agent hallucinated. Told *"do
not infer a receipt exists"*, it read "the receipt is already attached in the expense
system" and asserted `receipt_attached: true`, three runs out of three, approving an
$840 report with no receipt. The system now recovers from exactly that: attestable
facts come from the system of record, the model's version is a *claim*, and a claim
the record contradicts escalates to a human. See [EVALUATION.md](EVALUATION.md).

Most submissions will answer this criterion with a retry policy. Answering it with a
reproduced failure of your own agent, a fix at the architectural level, and a
regression gate is a different class of answer.

> **Note the prize table:** *Best Architectural Design* — $5,000, two awarded, to
> "top scoring projects in that judging criteria". That is the prize this project is
> best positioned for.

### Demo & Production Readiness — 30%

> "**The Proof of Action:** Does the video show an **unedited, live execution** of the
> agent performing its task (via terminal logs, database updates, or UI changes)?"

⚠️ **This corrects my earlier demo guidance.** I had told you to cut unwanted fixtures
out of beat 3. Don't. Beats 3 and 4 are each **one unbroken take** — no cuts inside
the execution, no speed-ups, no splicing a good run over a bad one. If a take goes
wrong, discard the take and reshoot it whole. [DEMO.md](DEMO.md) is updated.

Keep the terminal visible in frame during the radar take so the run is self-evidently
live rather than a screen recording of a rehearsal.

---

## Bonus points — the cheapest score on the board

Stage Three adds up to **1.0 point on a 5-point base**. That is a 20% swing for a
couple of hours of work, and most teams skip it because it isn't in the main form.

| Bonus | Points | Effort |
| :--- | :--- | :--- |
| Public content piece (blog / dev.to / YouTube) on how it was built | **0.2** | [EVALUATION.md](EVALUATION.md) is most of a post already — "we attacked our own agent and it approved an $840 expense" is a real story. Must be **public, not unlisted**, and must state it was created for this hackathon |
| Social post with `#AllThingsAgenticHackathon` | **0.2** | Ten minutes. LinkedIn or X |
| Each additional Google AI model (Gemma, Veo, Lyria) | **0.2 each, max 0.6** | Hardest of the three. A Gemma call somewhere real is the plausible one; do not bolt on a fake integration |

The first two are 0.4 points for well under two hours and carry no technical risk.
Do them.

---

## Ordered plan for the remaining time

1. **Redeploy** with the `records.py` fix, then `verify_deployed` (3/3) and
   `eval_claims --deployed` (2/2). New engine id, old one untouched. Do this first —
   everything downstream records against it.
2. **Delete the three stale engines** so the Console shot is clean.
3. **Generate Cloud Trace spans**, then confirm they are visible before recording.
4. **Record the video** to [DEMO.md](DEMO.md), beats 3 and 4 unbroken.
5. **Upload public to YouTube** early — processing takes hours.
6. **Share the private repo** with `testing@devpost.com` and `cloudhackathons@google.com`,
   verify in incognito.
7. **Fill the form**, attach `docs/architecture.png`, select Fortified Enterprise Fleet.
8. **Bonus:** blog post + social post. 0.4 points.
9. **Submit by 3 PM PT Aug 31.** Then stop touching the repo.
