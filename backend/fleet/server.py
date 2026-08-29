"""HTTP surface for the fleet. Serves the exact contract backend/devtools/local_server.py
serves, on the same port and paths, so switching the radar from stand-in to real fleet
is a matter of stopping one process and starting the other.

  GET  /events         SSE stream of spans (the radar's live feed)
  GET  /pending        report ids currently parked awaiting manager approval
  POST /approve/:id    resume a parked report as approved
  POST /deny/:id       resume a parked report as denied
  GET  /healthz        readiness, including whether GCP config resolved
"""

import json
import os
import queue
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import config, orchestrator, telemetry

PORT = 8000

# Two ways to drive the radar, same span contract out of both:
#
#   deterministic (default)  orchestrator.decide() — real Model Armor and Cloud DLP,
#                            no model, milliseconds per report, free apart from the
#                            two security calls.
#   live agent               live_agent.review() — the DEPLOYED agents, real Gemini
#                            turns and real tool calls, so the radar renders actual
#                            delegation. Several Gemini calls per report.
#
# FLEET_LIVE_AGENT=1 picks the second. It is opt-in because it costs money on a loop.
LIVE_AGENT = os.environ.get("FLEET_LIVE_AGENT", "").lower() in ("1", "true", "yes")

# The live path is far slower and costs per report, so it walks only the five demo
# fixtures and waits longer between them. The deterministic path can afford the lot.
LIVE_AGENT_INTERVAL_SECONDS = 25
LIVE_AGENT_REPORTS = (
    "EXP-2026-0001",
    "EXP-2026-0002",
    "EXP-2026-0003",
    "EXP-2026-0004",
    "EXP-2026-0005",
)

_pending = {}
_pending_lock = threading.Lock()


def load_fixtures():
    reports = []
    for path in sorted(config.FIXTURES_DIR.glob("*.json")):
        with open(path, "r", encoding="utf-8") as f:
            reports.append(json.load(f))
    if LIVE_AGENT:
        by_id = {r["report_id"]: r for r in reports}
        return [by_id[rid] for rid in LIVE_AGENT_REPORTS if rid in by_id]
    return reports


def reviewer():
    """The function that actually reviews a report, per the configured mode."""
    if LIVE_AGENT:
        from . import live_agent

        return live_agent.review
    return orchestrator.decide


def park(report_id, result):
    with _pending_lock:
        _pending[report_id] = result


def resolve_pending(report_id, decision):
    with _pending_lock:
        entry = _pending.pop(report_id, None)
    if entry is None:
        return None

    tracer = telemetry.tracer()
    with tracer.start_as_current_span(
        "execute_tool",
        attributes={"fleet.agent": "orchestrator", "fleet.report_id": report_id},
    ) as span:
        span.set_attribute("fleet.verdict", decision)
        span.set_attribute(
            "fleet.summary", f"Manager {decision} report {report_id} after escalation."
        )
    return {"report_id": report_id, "decision": decision}


def review_loop(interval_seconds=None):
    """Walk the fixtures on a loop so the radar always has traffic during a demo.
    Escalated reports are parked rather than re-reviewed, so an approval is a real
    resume rather than a fresh run over the same report.
    """
    reports = load_fixtures()
    if not reports:
        print("[server] no fixtures found; /events will stay idle")
        return
    if interval_seconds is None:
        interval_seconds = LIVE_AGENT_INTERVAL_SECONDS if LIVE_AGENT else 6
    review = reviewer()
    index = 0
    while True:
        report = reports[index % len(reports)]
        index += 1
        with _pending_lock:
            already_parked = report["report_id"] in _pending
        if not already_parked:
            try:
                result = review(report)
                if result["verdict"] == "escalated":
                    park(report["report_id"], result)
            except Exception as exc:  # noqa: BLE001
                print(f"[server] review of {report['report_id']} failed: {exc}")
        time.sleep(interval_seconds)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/events":
            self._stream_events()
        elif self.path == "/pending":
            with _pending_lock:
                self._json(200, {"pending": list(_pending.keys())})
        elif self.path == "/healthz":
            self._json(200, {
                "ok": True,
                "project": config.PROJECT_ID,
                "location": config.LOCATION,
                "memory_bank": bool(config.AGENT_ENGINE_ID),
            })
        else:
            self._decision_or_404()

    def do_POST(self):
        self._decision_or_404()

    def _decision_or_404(self):
        """The devtools contract used GET for approve/deny; POST is the correct verb
        for a state change. Accept both so the radar works against either backend.
        """
        for prefix, decision in (("/approve/", "approved"), ("/deny/", "denied")):
            if self.path.startswith(prefix):
                report_id = self.path[len(prefix):]
                resolved = resolve_pending(report_id, decision)
                if resolved:
                    self._json(200, {"ok": True, **resolved})
                else:
                    self._json(404, {"ok": False, "error": f"{report_id} is not pending"})
                return
        self._json(404, {"error": "not found"})

    def _stream_events(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(b": connected\n\n")
        self.wfile.flush()

        q = telemetry.subscribe()
        try:
            while True:
                try:
                    event_name, payload = q.get(timeout=15)
                except queue.Empty:
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
                    continue
                chunk = f"event: {event_name}\ndata: {json.dumps(payload)}\n\n"
                self.wfile.write(chunk.encode("utf-8"))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            telemetry.unsubscribe(q)

    def log_message(self, fmt, *args):
        pass


class Server(ThreadingHTTPServer):
    """A radar disconnecting mid-SSE is normal, not an incident. The default
    handler prints a full ConnectionResetError traceback for it, which on a demo
    screen reads as the backend crashing.
    """

    def handle_error(self, request, client_address):
        import sys

        exc = sys.exc_info()[0]
        if exc in (ConnectionResetError, BrokenPipeError):
            return
        super().handle_error(request, client_address)


def main():
    telemetry.init()
    threading.Thread(target=review_loop, daemon=True).start()
    print(f"[server] project {config.PROJECT_ID} ({config.LOCATION})")
    if LIVE_AGENT:
        print(
            f"[server] LIVE AGENT mode — driving deployed engine "
            f"{config.DEPLOYED_ENGINE_ID}, {LIVE_AGENT_INTERVAL_SECONDS}s between "
            f"reports. This costs Gemini calls on a loop; stop it when you are done."
        )
    else:
        print("[server] deterministic mode (set FLEET_LIVE_AGENT=1 for the real agents)")
    print(f"[server] SSE on http://localhost:{PORT}/events")
    Server(("", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
