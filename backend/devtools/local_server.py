"""Local reference implementation of the /events SSE pipeline (README Setup step 3),
built entirely from backend/fixtures/reports/*.json and policies/rules.yaml — no
Gemini, ADK, Model Armor, DLP, or GCP calls anywhere in this file. It exists to prove
the trace contract and orchestration sequencing end-to-end with zero cost while
credits are pending; it is NOT backend/fleet/server.py. Vidya's real server.py
replaces this wholesale once the ADK agents exist — same /events contract, real
Gemini extraction, real Model Armor + Cloud DLP instead of pii_scan.py's regex stand-in.

Run: python backend/devtools/local_server.py
Then point the frontend's Live mode at http://localhost:8000/events (same URL the
frontend already expects — see frontend/src/App.jsx EVENTS_URL).
"""

import json
import os
import queue
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from decision import decide
from rules_loader import load_rules

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FIXTURES_DIR = os.path.join(REPO_ROOT, "backend", "fixtures", "reports")
RULES_PATH = os.path.join(REPO_ROOT, "backend", "policies", "rules.yaml")
PORT = 8000
GAP_BETWEEN_REPORTS_S = 2.0

clients = []
clients_lock = threading.Lock()

# Local proof of the README's pause/resume story: "ESCALATED -> run pauses, session
# parked in Memory Bank... resumes days later on a manager FunctionResponse." Real
# implementation is ADK's tool_context.request_confirmation() inside a
# LongRunningFunctionTool (Vidya's Day 5) — this just proves the same shape end-to-end
# with a manual HTTP call standing in for the manager's response, so the mechanic is
# de-risked before that real wiring exists.
pending_approvals = {}  # report_id -> {"trace_id": ..., "root_id": ...}
pending_lock = threading.Lock()


def now_ms():
    return int(time.time() * 1000)


def broadcast(event_name, span):
    frame = f"event: {event_name}\ndata: {json.dumps(span)}\n\n"
    with clients_lock:
        dead = []
        for q in clients:
            try:
                q.put_nowait(frame)
            except queue.Full:
                dead.append(q)
        for q in dead:
            clients.remove(q)


def load_fixtures():
    files = sorted(f for f in os.listdir(FIXTURES_DIR) if f.endswith(".json"))
    reports = []
    for fname in files:
        with open(os.path.join(FIXTURES_DIR, fname), "r", encoding="utf-8") as f:
            reports.append(json.load(f))
    return reports


def span_start(trace_id, span_id, parent_id, name, agent, report_id):
    s = {
        "trace_id": trace_id,
        "span_id": span_id,
        "parent_id": parent_id,
        "name": name,
        "agent": agent,
        "report_id": report_id,
        "start_ms": now_ms(),
        "end_ms": None,
        "status": "OK",
        "attributes": {},
    }
    broadcast("span_start", s)
    return s


def span_end(started, status="OK", attributes=None):
    started["end_ms"] = now_ms()
    started["status"] = status
    started["attributes"] = attributes or {}
    broadcast("span_end", started)


def orchestrate(report, rules):
    trace_id = uuid.uuid4().hex
    root_id = uuid.uuid4().hex
    report_id = report["report_id"]

    root = span_start(trace_id, root_id, None, "invoke_agent", "orchestrator", report_id)

    screen_id = uuid.uuid4().hex
    screen_span = span_start(trace_id, screen_id, root_id, "execute_tool", "screening", report_id)
    time.sleep(0.25)
    result = decide(report, rules)
    span_end(screen_span, attributes={"violations": result["violations"], "summary": result["summary"]})

    pii_id = uuid.uuid4().hex
    pii_span = span_start(trace_id, pii_id, root_id, "execute_tool", "pii_compliance", report_id)
    time.sleep(0.25)

    if result["verdict"] == "blocked":
        span_end(
            pii_span,
            status="BLOCKED",
            attributes={
                "verdict": "blocked",
                "armor_verdict": result["armor_verdict"],
                "summary": result["summary"],
            },
        )
    else:
        span_end(
            pii_span,
            attributes={
                "verdict": result["verdict"],
                "dlp_redactions": result["dlp_redactions"],
                "summary": result["summary"],
            },
        )

    if result["verdict"] == "escalated":
        with pending_lock:
            pending_approvals[report_id] = {
                "trace_id": trace_id,
                "root_id": root_id,
                "start_ms": root["start_ms"],
            }
        # Root span deliberately stays open (no span_end here) — it represents the
        # run genuinely parked awaiting a manager, not a fixed sleep. resolve_pending()
        # closes it later, whenever /approve or /deny actually gets called.
        return

    time.sleep(0.05)
    span_end(root)


def resolve_pending(report_id, decision_label):
    with pending_lock:
        entry = pending_approvals.pop(report_id, None)
    if entry is None:
        return False

    resume_id = uuid.uuid4().hex
    resume_span = span_start(
        entry["trace_id"], resume_id, entry["root_id"], "execute_tool", "orchestrator", report_id
    )
    time.sleep(0.05)
    span_end(
        resume_span,
        attributes={
            "manager_decision": decision_label,
            "summary": f"Manager {decision_label} after review — run resumed.",
        },
    )

    root_span = {
        "trace_id": entry["trace_id"],
        "span_id": entry["root_id"],
        "parent_id": None,
        "name": "invoke_agent",
        "agent": "orchestrator",
        "report_id": report_id,
        "start_ms": entry["start_ms"],
        "status": "OK",
        "attributes": {},
    }
    span_end(root_span, attributes={"manager_decision": decision_label})
    return True


def run_loop():
    rules = load_rules(RULES_PATH)
    reports = load_fixtures()
    if not reports:
        print(f"No fixtures found in {FIXTURES_DIR}")
        return
    i = 0
    while True:
        report = reports[i % len(reports)]
        with pending_lock:
            already_pending = report["report_id"] in pending_approvals
        if not already_pending:
            orchestrate(report, rules)
        i += 1
        time.sleep(GAP_BETWEEN_REPORTS_S)


class EventsHandler(BaseHTTPRequestHandler):
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
            return

        if self.path == "/pending":
            with pending_lock:
                report_ids = list(pending_approvals.keys())
            self._json(200, {"pending": report_ids})
            return

        if self.path.startswith("/approve/") or self.path.startswith("/deny/"):
            decision_label = "approved" if self.path.startswith("/approve/") else "denied"
            report_id = self.path.rsplit("/", 1)[-1]
            resolved = resolve_pending(report_id, decision_label)
            if resolved:
                self._json(200, {"ok": True, "report_id": report_id, "decision": decision_label})
            else:
                self._json(404, {"ok": False, "error": f"{report_id} is not pending approval"})
            return

        self.send_response(404)
        self.end_headers()

    def _stream_events(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        q = queue.Queue(maxsize=1000)
        with clients_lock:
            clients.append(q)
        try:
            self.wfile.write(b": connected\n\n")
            while True:
                frame = q.get()
                self.wfile.write(frame.encode("utf-8"))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            with clients_lock:
                if q in clients:
                    clients.remove(q)

    def log_message(self, fmt, *args):
        pass  # keep stdout clean; loop already prints per-report progress if needed


if __name__ == "__main__":
    threading.Thread(target=run_loop, daemon=True).start()
    server = ThreadingHTTPServer(("localhost", PORT), EventsHandler)
    print(f"Local reference /events server on http://localhost:{PORT}/events")
    server.serve_forever()
