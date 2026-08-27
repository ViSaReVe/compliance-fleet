"""The seam between ADK's OpenTelemetry spans and the radar's trace contract.

ADK emits spans automatically (invoke_agent, call_llm, execute_tool,
generate_content) with no configuration. Two things are missing for the radar:
ADK spans carry neither `agent` nor `report_id` as top-level fields, and nothing
streams them anywhere a browser can read.

This module solves both with one SpanProcessor and two sinks:

    ADK spans ──┬─► CloudTraceSpanExporter   (audit trail, GCP proof for the demo)
                └─► RadarSpanProcessor ─► in-process queues ─► SSE ─► radar

Because both sinks read the same spans, anything the radar draws is provably in
Cloud Trace. There is no second, parallel instrumentation path to drift.
"""

import contextvars
import queue
import threading

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanProcessor

from . import config

# ADK has no notion of "which of our three agents is running" or "which expense
# report is this". Both are set by the orchestrator around each step and read back
# here, because contextvars propagate correctly across the async boundaries ADK
# uses internally.
current_agent = contextvars.ContextVar("current_agent", default="orchestrator")
current_report = contextvars.ContextVar("current_report", default=None)

# Span names the radar has a node for. Anything else still streams — the frontend
# ignores names it cannot place — but these are the ones that drive the sweep.
RADAR_SPAN_NAMES = ("invoke_agent", "call_llm", "execute_tool", "generate_content")

_subscribers = []
_subscribers_lock = threading.Lock()


def subscribe():
    """Register an SSE client. Returns a queue the server drains until disconnect."""
    q = queue.Queue(maxsize=1000)
    with _subscribers_lock:
        _subscribers.append(q)
    return q


def unsubscribe(q):
    with _subscribers_lock:
        if q in _subscribers:
            _subscribers.remove(q)


def broadcast(event_name, payload):
    """Fan out one event to every connected radar. Never blocks the agent thread:
    a client too slow to keep up loses events rather than stalling the fleet.
    """
    with _subscribers_lock:
        targets = list(_subscribers)
    for q in targets:
        try:
            q.put_nowait((event_name, payload))
        except queue.Full:
            pass


def _hex(value, width):
    return format(value, f"0{width}x")


def _flatten(span, phase):
    """Reshape an OTel ReadableSpan into the locked trace contract.

    Field-for-field identical to what backend/devtools/local_server.py emits, so
    the frontend needs no change when the real fleet replaces the stand-in.
    """
    ctx = span.get_span_context()
    parent = span.parent
    attributes = dict(span.attributes or {})

    agent = attributes.get("fleet.agent") or current_agent.get()
    report_id = attributes.get("fleet.report_id") or current_report.get()

    payload = {
        "trace_id": _hex(ctx.trace_id, 32),
        "span_id": _hex(ctx.span_id, 16),
        "parent_id": _hex(parent.span_id, 16) if parent else None,
        "name": span.name,
        "agent": agent,
        "report_id": report_id,
        "start_ms": span.start_time // 1_000_000 if span.start_time else None,
        "end_ms": None,
        "status": "OK",
        "attributes": {},
    }

    if phase == "end":
        payload["end_ms"] = span.end_time // 1_000_000 if span.end_time else None
        # fleet.* attributes are ours; everything else is ADK/GenAI internals the
        # radar has no use for and which can be large (full prompt text).
        payload["attributes"] = {
            key[len("fleet.") :]: value
            for key, value in attributes.items()
            if key.startswith("fleet.") and key not in ("fleet.agent", "fleet.report_id")
        }
        payload["status"] = attributes.get("fleet.status", "OK")

    return payload


class RadarSpanProcessor(SpanProcessor):
    """Streams span lifecycle to connected radars as it happens.

    on_start fires when work begins, which is what makes a node pulse at the right
    moment; waiting for on_end would show every agent lighting up only after it had
    already finished.
    """

    def on_start(self, span, parent_context=None):
        broadcast("span_start", _flatten(span, "start"))

    def on_end(self, span):
        broadcast("span_end", _flatten(span, "end"))

    def shutdown(self):
        pass

    def force_flush(self, timeout_millis=30000):
        return True


_initialised = False


def init(export_to_cloud_trace=True):
    """Install the tracer provider. Idempotent — safe to call from server, deploy,
    and tests without stacking duplicate processors.
    """
    global _initialised
    if _initialised:
        return
    provider = TracerProvider()
    provider.add_span_processor(RadarSpanProcessor())

    if export_to_cloud_trace:
        try:
            from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter

            provider.add_span_processor(
                BatchSpanProcessor(CloudTraceSpanExporter(project_id=config.PROJECT_ID))
            )
        except Exception as exc:  # noqa: BLE001 - never let telemetry break the fleet
            print(f"[telemetry] Cloud Trace export disabled: {exc}")

    trace.set_tracer_provider(provider)
    _initialised = True


def tracer():
    return trace.get_tracer("compliance-fleet")
