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

from pii_scan import detect_injection, redact
from rule_engine import check_policy, summarize
from rules_loader import load_rules

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FIXTURES_DIR = os.path.join(REPO_ROOT, "backend", "fixtures", "reports")
RULES_PATH = os.path.join(REPO_ROOT, "backend", "policies", "rules.yaml")
PORT = 8000
GAP_BETWEEN_REPORTS_S = 2.0

clients = []
clients_lock = threading.Lock()


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
    violations = check_policy(report, rules)
    span_end(screen_span, attributes={"violations": violations, "summary": summarize(report, violations)})

    pii_id = uuid.uuid4().hex
    pii_span = span_start(trace_id, pii_id, root_id, "execute_tool", "pii_compliance", report_id)
    time.sleep(0.25)

    if detect_injection(report.get("description")):
        span_end(
            pii_span,
            status="BLOCKED",
            attributes={
                "verdict": "blocked",
                "armor_verdict": "PROMPT_INJECTION_BLOCKED",
                "summary": f"Model Armor intercepted: \"{report['description']}\".",
            },
        )
    else:
        combined_text = " ".join(filter(None, [report.get("receipt_ocr_text"), report.get("description")]))
        _, redaction_count = redact(combined_text)

        if "OVER_LIMIT_NO_PREAPPROVAL" in violations:
            verdict = "escalated"
        elif violations:
            verdict = "flagged"
        else:
            verdict = "approved"

        summary = summarize(report, violations)
        if redaction_count:
            summary = f"Redacted {redaction_count} item(s) before persistence. {summary}"

        span_end(
            pii_span,
            attributes={"verdict": verdict, "dlp_redactions": redaction_count, "summary": summary},
        )

    time.sleep(0.05)
    span_end(root)


def run_loop():
    rules = load_rules(RULES_PATH)
    reports = load_fixtures()
    if not reports:
        print(f"No fixtures found in {FIXTURES_DIR}")
        return
    i = 0
    while True:
        orchestrate(reports[i % len(reports)], rules)
        i += 1
        time.sleep(GAP_BETWEEN_REPORTS_S)


class EventsHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/events":
            self.send_response(404)
            self.end_headers()
            return

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
