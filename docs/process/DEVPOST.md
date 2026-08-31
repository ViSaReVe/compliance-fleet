# Devpost submission — copy and paste

Every field, with the text already written. Work down the page.

---

## Project details

**Project name**

```
Expense Compliance Fleet + Agent Radar
```

**Elevator pitch** *(if the form asks for a one-liner)*

```
A governed fleet of ADK agents that screens expense reports, blocks prompt injection at the boundary, redacts PII before persistence, and parks escalations for a human — rendered live as a reasoning-chain radar.
```

**Built with** — 18 tags, all genuinely used. Limit is 25, so there is room; do not
pad it with things the project does not use.

Ordered deliberately: the track's own stack first, since that is what a judge scanning
the tag row is looking for, then the standards, then the plumbing.

```
gemini, vertex-ai, google-adk, google-cloud, agent-runtime, model-armor, cloud-dlp,
memory-bank, agent-registry, agent-identity, cloud-trace, opentelemetry,
server-sent-events, cloud-storage, python, react, vite, javascript
```

The field takes one tag at a time — type it, then **Enter or comma**. Pasting the
whole line usually splits correctly, but check the row afterwards: if it came through
as one long tag instead of eighteen, clear it and add them individually. Devpost
autocompletes tags it already knows; anything it does not recognise gets created as a
new tag, which is fine.

---

## About the project

**Paste [`devpost-story.md`](devpost-story.md) into the story field, whole.** It is a
standalone file so there is no ambiguity about where to start and stop copying.

It uses only the Markdown Devpost guarantees — `##` headings, bold, italics, inline
code, blockquotes. **No tables and no fenced code blocks anywhere**, because Devpost's
own docs class those as *extended* syntax with the caveat that "not all Markdown
applications support these elements", and a submission is a bad place to find out.
Devpost's form hint uses `## Headline`, so the sections are H2 and there is no H1.

It uses **Devpost's own seven-heading template** — Inspiration, What it does, How we
built it, Challenges we ran into, Accomplishments that we're proud of, What we
learned, What's next — with no headings added or dropped. That is the shape a judge
expects, and a story that answers the prompts in order is easier to score than one
that reorganises them.

~1,300 words. The four things the rules ask for by name are all present: features and
functionality (*What it does*), technologies used (*How we built it*), other data
sources (*How we built it*, stated as none — synthetic fixtures), and findings and
learnings (*Challenges*, *Accomplishments* and *What we learned*, which between them
carry the real story).

**After pasting, use Devpost's preview** to confirm the blockquotes and headings
rendered before you submit.

## Additional info

| Field | Answer |
| :--- | :--- |
| Category | **Fortified Enterprise Fleet** |
| Submitter type | Team of individuals |
| Country | United States |
| Project start date | *(a date inside Aug 3–31, 2026)* |
| Code repo | `https://github.com/ViSaReVe/compliance-fleet` — **private**, must be shared with `testing@devpost.com` and `cloudhackathons@google.com` |
| Reproducible testing instructions in README? | **Yes** |
| Hosted project URL | *(leave empty — deliberate, see SUBMISSION.md)* |
| Google SDK used | **Agent Development Kit (ADK)** |
| Google Cloud services | Agent Runtime, Cloud Storage, Cloud Trace. *(None of the five checkboxes apply; the rules say "such as", which is non-exhaustive — see SUBMISSION.md)* |
| Architecture diagram | **upload** `docs/architecture.png` — attached, not linked |
| Google AI models | Gemini 3.5 Flash |
| Startup prize | not opting in |

**Testing instructions** *(judges-only field)*

```
No login required. The repo README has full spin-up instructions.

Fastest path with no Google Cloud account at all — the radar plus a zero-dependency
reference backend, on system python:

  python3 backend/devtools/local_server.py
  cd frontend && npm install && npm run dev     # open http://localhost:5173, click Live

Policy evaluation, no cloud calls:

  python3 backend/devtools/run_eval.py    # 13/13
  python -m fleet.eval_claims             # 51/51 — claims, trace invariants, cross-product

With a Google Cloud project (see README Setup), the same radar streams from the
deployed ADK agents on Agent Runtime:

  FLEET_LIVE_AGENT=1 python -m fleet.server

And the deployed engine can be verified directly:

  python -m fleet.verify_deployed -k 3    # 3/3 at pass^3
```

---

## Order of operations

1. **Upload the video to YouTube, PUBLIC.** Captions on. Do this first — processing
   takes hours.
2. **Share the private repo** with both addresses, then check the link in an incognito
   window.
3. Paste the story, fill Additional Info, **upload `docs/architecture.png`**.
4. **Select the category.** It starts unselected and is easy to miss.
5. **Confirm Sohan has accepted** the team invite — added is not the same as accepted.
6. Submit. Aim for **3 PM PT**, not 5.
7. Stop touching the repo. Judging runs to **Oct 1** and the project must stay
   testable that whole time.
