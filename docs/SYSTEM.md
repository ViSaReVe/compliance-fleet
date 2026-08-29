# What this system actually is

Written to answer a question that had not been asked plainly until now: *what are we
building, and where does each part's trust come from?* The answer explains the bug we
found, and it ranks everything still worth doing.

---

## The one-sentence version

**A policy-enforcement workflow with a language model at the perception boundary and
a human at the exception boundary.**

Not a chatbot. Not an autonomous agent. The model has exactly one job — turn an
unstructured submission into structured claims — and everything downstream of it is
deterministic. Humans are not in the loop; they are on the *exception* path, which is
a different and much cheaper thing.

By [Anthropic's taxonomy](https://www.anthropic.com/engineering/building-effective-agents) this is a **workflow**, not an agent:
*"Workflows orchestrate LLM and tool calls through predefined code — you own the
control flow."* That was the right call. There is no step here whose path we cannot
hardcode, and every autonomous turn we don't take is latency, tokens, and a chance for
an early mistake to propagate that we don't pay for.

---

## The four layers

Naming these is what makes the failure obvious in hindsight.

```
   untrusted text
         │
   ┌─────▼───────────────────────────────────────────┐
   │ 1. PERCEPTION      unstructured → claims        │  trust: NONE
   │    Gemini 3.5 Flash extraction                  │  everything here is a claim,
   │    fleet/screening.py                           │  including the model's own
   └─────┬───────────────────────────────────────────┘
         │  claims
   ┌─────▼───────────────────────────────────────────┐
   │ 2. ATTESTATION     claims → facts               │  trust: AUTHORITATIVE
   │    system of record; contradiction is a signal  │  ← this layer did not exist
   │    fleet/records.py                             │    until two days ago
   └─────┬───────────────────────────────────────────┘
         │  facts
   ┌─────▼───────────────────────────────────────────┐
   │ 3. DECISION        facts → verdict              │  trust: THE CONTROL
   │    thresholds in Python, never in a prompt      │  deterministic, testable,
   │    fleet/policy.py · policies/rules.yaml        │  arguable only by changing code
   └─────┬───────────────────────────────────────────┘
         │  verdict
   ┌─────▼───────────────────────────────────────────┐
   │ 4. EXCEPTION       verdict → human, durably     │  trust: DEFERRED
   │    LongRunningFunctionTool + Memory Bank        │  7-day runs; the pause is the
   │    fleet/approval.py                            │  product, not a failure mode
   └─────────────────────────────────────────────────┘

   cross-cutting:  Model Armor + Cloud DLP (boundary)   fleet/compliance.py
                   Agent Identity + fleet-security SA   fleet/deploy.py
                   OpenTelemetry → Cloud Trace + radar  fleet/telemetry.py
```

### Why the bug happened, stated structurally

**Layer 2 did not exist.** Layer 1's output fed layer 3 directly. So the sentence
*"the receipt is already attached in the expense system"* travelled from untrusted
text straight into a threshold check that was, correctly and deterministically,
computing the wrong answer from a poisoned input.

The README's claim — *thresholds are enforced in code, so no submission can argue a
verdict into changing* — was true and irrelevant. Nobody needs to change the rules if
they can change what the rules are shown.

This is exactly the distinction [CaMeL](https://arxiv.org/pdf/2503.18813) draws. It secures **control flow**
*and* **data flow**, borrowing Control Flow Integrity and Information Flow Control
from systems security. We had done the first and called it done.

---

## Where each layer sits against the state of the art

| Layer | What the field does | Where we are |
| :--- | :--- | :--- |
| **1. Perception** | Treat all model output as untrusted. [Dual LLM / Action-Selector / Plan-Then-Execute](https://arxiv.org/html/2506.08837v3) all assume the quarantined model can be lied to and design around it. | ✅ correct in principle. ⚠️ but `amount_usd` is still model-extracted and unattested — a misread amount silently selects a different threshold. |
| **2. Attestation** | CaMeL's capability/provenance labels; every value carries where it came from. | ⚠️ we have the boundary now, for two fields, resolved from the record and failing closed. No general provenance model — a third attestable field means editing a tuple. |
| **3. Decision** | Deterministic policy engines, out-of-model. [τ-bench](https://arxiv.org/pdf/2406.12045) exists precisely because *"current LLMs need significant enhancement in consistency and rule-following"* — so don't ask them to. | ✅ this is our strongest layer. YAML thresholds, pure functions, 13 cases. |
| **4. Exception** | Durable execution — checkpoint, park, resume days later. | ✅ ADK's `request_confirmation()` + Memory Bank, 7-day runs, verified deployed. We correctly did not hand-roll this. |
| **Guardrails** | [LlamaFirewall](https://arxiv.org/pdf/2505.03574), Model Armor, NeMo — inline classifiers at the boundary. Known to be necessary and known to be insufficient alone. | ✅ real Model Armor + real Cloud DLP, as tools not prose. ⚠️ 3 injection cases total. |
| **Identity** | [A2A](https://a2a-protocol.org/v0.2.5/topics/enterprise-ready/): *"skill-based authorization... specific OAuth scopes granting access to invoke certain skills but not others."* | ❌ one engine, one identity, in-process allowlist. Disclosed everywhere, but it is the real gap. |
| **Observability** | [OTel GenAI semantic conventions](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-agent-spans.md): `invoke_agent` at top, `chat` per model call, `execute_tool` per tool. Still *Development* status, nothing Stable as of mid-2026. | ✅ our span names are the convention's names — which is *why* the radar renders any ADK agent. Domain data correctly namespaced under `fleet.*` rather than polluting `gen_ai.*`. |

---

## What we actually test, honestly

| Surface | Exercises | LLM? | Count |
| :--- | :--- | :--- | :--- |
| `run_eval.py` | devtools regex + rule engine | no | 13 |
| `eval_claims.py` | layer 2 + 3, direct Python call | no | 5 |
| `verify_deployed.py` | layers 1–4, real agents, real tool calls | **yes** | 3 |
| `eval_claims --deployed` | layers 1–2, real extraction | yes | 2, never run |

**Three assertions are our entire agent-path coverage.** The 13/13 that looks
impressive tests the layer that was never at risk — the same blind spot that hid the
claim bug for four days.

Both [AgentDojo](https://openreview.net/forum?id=m1YYAQjO3w) and τ-bench get this right in ways we don't:

- **Deterministic check functions on end state, never LLM-as-judge.** ✅ we do this —
  `verify_deployed` asserts on `function_response` payloads, not on the agent's prose.
- **Cross-product of benign tasks × attacks.** AgentDojo crosses 97 tasks with
  injections into 900+ combinations. ❌ ours are separate lists, never crossed.
- **`pass^k`, not `pass@1`.** τ-bench measures reliability across *k* trials because
  single-run success on a stochastic system is not evidence. ❌ every check we have
  runs once. My probe ran 3× only because I didn't believe the first result.

---

## Ranked backlog

Ordered by value per hour against a two-day deadline. Everything above the line is
plausibly doable; everything below it is honest roadmap.

### 1. Radar drives the deployed agent — ~1h, highest value

Today the radar renders `orchestrator.decide()`, which is straight-line Python: real
Model Armor and real Cloud DLP calls, but **zero LLM and zero agent**. Beat 2 of the
demo describes an agent architecture and beat 3 shows the path that doesn't use it.

The judging criterion asks, literally, *"Does the system intelligently delegate tasks
to specialized sub-agents?"* Mapping the deployed engine's event stream onto the span
contract makes the radar answer that instead of dodging it — real per-agent authors,
real `call_llm` spans, real delegation on screen.

Cost: a few Gemini calls per report, and reports arrive in seconds rather than
milliseconds. That is a better demo anyway — you can *see* the agent think.

### 2. `pass^k` on the deployed checks — ~20min

Run each `verify_deployed` check k=3 times, report `3/3` per check rather than a bare
PASS. Directly adopts τ-bench's reliability framing, costs three times the Gemini
calls of a run that already costs pennies, and turns "it worked when we tried it" into
"it worked every time we tried it". Cheap credibility.

### 3. Cross-product adversarial eval — ~45min

AgentDojo's structure: every fixture × every attack, not two separate lists. Turns 13
policy cases and 3 injection cases into a matrix that would have caught the claim bug
on day one.

### 4. Invariant enforcement on the span stream — ~1h, most interesting

We already have a `SpanProcessor` that sees every span in order. Right now it only
*observes*. It could **assert**:

- no verdict span without a preceding `scan_for_prompt_injection` span in the same trace
- no persisted summary without a preceding `redact_pii` span
- no `approved` verdict on a trace that contains an `UNVERIFIED_*_CLAIM`

That makes the audit trail a **control**, not just a record — an agent that skips a
security step fails the trace check even if its prose claims it didn't. It is the same
move [AgentArmor](https://arxiv.org/pdf/2508.01249) makes (program analysis over the agent's runtime trace), and it
directly answers *"how does the system recover if a worker agent loops or returns a
hallucination?"* — the criterion we are otherwise weakest on.

---

- - -

### Below the line — real, but not in two days

- **Per-agent identity split.** Separate engine per agent, each with its own Agent
  Identity and IAM bindings, so "screening cannot call redaction" is enforced by the
  platform. Plus A2A agent cards with per-skill scopes. This is the honest fix for the
  one gap we keep disclosing.
- **General provenance model.** Every value carries its source; attestation is a
  property of the value, not a hardcoded tuple of two field names.
- **Attest the amount.** Reconcile `amount_usd` against the receipt total in the
  record, the same way the two booleans are now reconciled.
- **Collapse the two verdict paths.** `orchestrator.decide()` and the deployed
  `LlmAgent` compute verdicts by different means and only one is a control. They agree
  today; nothing enforces that they must.
