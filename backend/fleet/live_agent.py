"""Drive the DEPLOYED agents and render their real reasoning on the radar.

`orchestrator.decide()` is straight-line Python. It makes real Model Armor and real
Cloud DLP calls, and its spans are real OpenTelemetry spans — but no model runs and no
agent is involved. So the radar has been showing a path that does not exercise the
thing the architecture diagram is about, and "does the system intelligently delegate
tasks to specialized sub-agents" had no answer on screen.

This module closes that. It sends a report to the deployed reasoning engine, reads the
event stream back, and turns each event into a real OTel span as it arrives:

    invoke_agent                 orchestrator, one per report
      call_llm                   one per model turn, attributed to the sub-agent
      execute_tool               one per tool call, opened on function_call and
                                 closed on the matching function_response

Which means the radar now pulses on the actual agent handoff — screening lights up
because the *screening agent* is talking, not because a Python function is. And
because these are ordinary spans through the same provider, they reach Cloud Trace by
the same path as everything else. One SpanProcessor, two sinks, still true.

The verdict is still not the model's opinion. It is derived here, deterministically,
from the tool results the agents actually got back — a blocked Model Armor scan is
blocked whatever the agent then writes about it. The model reasons; the code decides;
this module only reports what both did.

Cost: several Gemini calls per report. `server.py` runs this on a much longer interval
than the deterministic path for that reason.
"""

import json

from opentelemetry import trace

from . import config, policy, telemetry
from .verify_deployed import stream_query

# Sub-agent names the radar has nodes for. An event from anywhere else is attributed
# to the orchestrator rather than dropped, so an added agent degrades to a visible
# blip instead of vanishing.
KNOWN_AGENTS = ("screening", "pii_compliance")


def prompt_for(report):
    """Render a fixture as the free text a submitter would actually type.

    Deliberately prose, not JSON. Handing the agent pre-structured fields would skip
    extraction — which is the whole point of having a model in the loop, and the layer
    where the claim attack lives.
    """
    parts = [
        f"Review expense report {report['report_id']}: "
        f"${report['amount_usd']:,.2f} {report.get('category', 'expense')}"
    ]
    if report.get("merchant"):
        parts.append(f" at {report['merchant']}")
    if report.get("description"):
        parts.append(f". Description: {report['description']!r}")
    if report.get("receipt_ocr_text"):
        parts.append(f" Receipt OCR text: {report['receipt_ocr_text']!r}")
    parts.append(
        f" Receipt attached: {bool(report.get('receipt_attached'))}."
        f" Pre-approval requested: {bool(report.get('requested_preapproval'))}."
    )
    return "".join(parts)


def _agent_of(event, fallback="orchestrator"):
    author = event.get("author")
    return author if author in KNOWN_AGENTS else fallback


def _derive(tool_results, parked):
    """The verdict, from what the tools returned — never from what the agent wrote.

    A deployed LlmAgent will write "Model Armor: Passed" having called nothing, so its
    prose is not evidence. These are the values the security services handed back.
    """
    armor = (tool_results.get("scan_for_prompt_injection") or [{}])[0] or {}
    if armor.get("blocked"):
        return "blocked", armor.get("armor_verdict"), []

    policy_result = (tool_results.get("check_expense_policy") or [{}])[0] or {}
    violations = list(policy_result.get("violations") or [])

    if parked or policy.escalates(violations):
        return "escalated", None, violations
    if violations:
        return "flagged", None, violations
    return "approved", None, violations


def review(report):
    """Run one report through the deployed fleet, emitting spans as it happens.

    Returns the same shape `orchestrator.decide()` returns, so `server.py` can drive
    either path without knowing which it has.
    """
    tracer = telemetry.tracer()
    report_id = report.get("report_id") or ""
    engine_id = config.DEPLOYED_ENGINE_ID
    if not engine_id:
        raise RuntimeError(
            "FLEET_ENGINE_ID is not set; live agent mode needs a deployed engine. "
            "Run `python -m fleet.deploy` or unset FLEET_LIVE_AGENT."
        )

    token = telemetry.current_report.set(report_id)
    root = tracer.start_span(
        "invoke_agent",
        attributes={"fleet.agent": "orchestrator", "fleet.report_id": report_id},
    )
    root_context = trace.set_span_in_context(root)

    open_tools = {}      # function_call id -> live execute_tool span
    tool_results = {}    # tool name -> [response, ...]
    parked = []
    redactions = 0

    try:
        for event in stream_query(engine_id, prompt_for(report), user_id="radar"):
            agent = _agent_of(event)
            parked.extend(event.get("long_running_tool_ids") or [])

            # A model turn. One span per turn so the radar shows the agent thinking,
            # not just the tools firing. ADK's own name for this span is call_llm.
            if event.get("model_version"):
                llm_span = tracer.start_span(
                    "call_llm",
                    context=root_context,
                    attributes={
                        "fleet.agent": agent,
                        "fleet.report_id": report_id,
                        "fleet.model": event["model_version"],
                    },
                )
                llm_span.end()

            for part in (event.get("content") or {}).get("parts") or []:
                call = part.get("function_call")
                if call:
                    span = tracer.start_span(
                        "execute_tool",
                        context=root_context,
                        attributes={
                            "fleet.agent": agent,
                            "fleet.report_id": report_id,
                            "fleet.tool": call.get("name") or "",
                            "fleet.summary": f"{agent} called {call.get('name')}",
                        },
                    )
                    # Keyed by call id so a tool called twice in one run closes the
                    # right span; the runtime reuses names but not ids.
                    open_tools[call.get("id")] = span
                    continue

                response = part.get("function_response")
                if response:
                    name = response.get("name") or ""
                    payload = response.get("response") or {}
                    tool_results.setdefault(name, []).append(payload)
                    redactions = max(redactions, int(payload.get("redaction_count") or 0))

                    span = open_tools.pop(response.get("id"), None)
                    if span is None:
                        continue
                    span.set_attribute("fleet.summary", _tool_summary(name, payload))
                    if payload.get("blocked"):
                        span.set_attribute("fleet.status", "BLOCKED")
                        span.set_attribute(
                            "fleet.armor_verdict", payload.get("armor_verdict") or ""
                        )
                    if payload.get("violations"):
                        span.set_attribute(
                            "fleet.violations", list(payload["violations"])
                        )
                    span.end()

        # A tool the runtime never answered — a parked long-running call is the normal
        # case. Close them so the radar does not leave a node lit forever.
        for span in open_tools.values():
            span.set_attribute("fleet.summary", "awaiting a response — run parked")
            span.end()

        verdict, armor_verdict, violations = _derive(tool_results, parked)
        summary = _summarize(report, verdict, violations, armor_verdict, redactions)

        result = {
            "verdict": verdict,
            "violations": violations,
            "armor_verdict": armor_verdict,
            "dlp_redactions": redactions,
            "summary": summary,
        }
        root.set_attribute("fleet.verdict", verdict)
        root.set_attribute("fleet.summary", summary)
        root.set_attribute("fleet.violations", list(violations))
        if armor_verdict:
            root.set_attribute("fleet.armor_verdict", armor_verdict)
            root.set_attribute("fleet.status", "BLOCKED")
        return result
    finally:
        root.end()
        telemetry.current_report.reset(token)


def _tool_summary(name, payload):
    if name == "scan_for_prompt_injection":
        return (
            f"Model Armor: {payload.get('armor_verdict')}"
            if payload.get("blocked")
            else "Model Armor: no injection detected"
        )
    if name == "redact_pii":
        count = payload.get("redaction_count") or 0
        return f"Cloud DLP redacted {count} item(s)" if count else "Cloud DLP: nothing to redact"
    if name == "check_expense_policy":
        return payload.get("summary") or json.dumps(payload)[:200]
    if name in ("request_manager_approval", "adk_request_confirmation"):
        # Raw JSON here reads as debug output on a demo screen, and this is the one
        # step in the run a human is meant to understand at a glance.
        return "Escalated to a human manager — run parked awaiting their decision"
    return json.dumps(payload)[:200]


def _summarize(report, verdict, violations, armor_verdict, redactions):
    if verdict == "blocked":
        return f'Model Armor intercepted: "{report.get("description") or ""}".'
    text = policy.summarize(
        {"amount_usd": report.get("amount_usd") or 0}, violations
    )
    if redactions:
        text = f"Redacted {redactions} item(s) before persistence. {text}"
    return text
