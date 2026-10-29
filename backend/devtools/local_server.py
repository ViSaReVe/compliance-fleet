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

import itertools
import json
import os
import queue
import threading
import time
import uuid
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import agent_gateway
import agent_identity
import agent_registry
import agents
import payouts
import security_demos
from rule_engine import summarize

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
pending_approvals = {}  # report_id -> {"kind": "expense"|"payout", "trace_id", "root_id", ...}
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


# Spans of traces that are still open, so a radar that connects late can be caught up.
# Without this a browser opened after a report parked sees only its newest span: a payout
# awaiting authorization with the verdict reading "pending", because the pii span that
# carried "approved" streamed before it connected. A trace leaves this table the moment
# its root span closes, so it holds only what is genuinely parked or in flight.
_trace_spans = {}
_trace_lock = threading.Lock()


def _remember(span):
    with _trace_lock:
        if span["parent_id"] is None:
            _trace_spans.pop(span["trace_id"], None)
        else:
            _trace_spans.setdefault(span["trace_id"], []).append(dict(span))


def backlog_frames():
    """span_end frames for every open trace that is parked on a person."""
    with pending_lock:
        trace_ids = [entry["trace_id"] for entry in pending_approvals.values()]
    with _trace_lock:
        spans = [sp for tid in trace_ids for sp in _trace_spans.get(tid, [])]
    return [f"event: span_end\ndata: {json.dumps(sp)}\n\n" for sp in spans]


def span_end(started, status="OK", attributes=None):
    started["end_ms"] = now_ms()
    started["status"] = status
    started["attributes"] = attributes or {}
    _remember(started)
    broadcast("span_end", started)


def _park(kind, ctx, **extra):
    with pending_lock:
        pending_approvals[ctx["report"]["report_id"]] = {
            "kind": kind,
            "trace_id": ctx["trace_id"],
            "root_id": ctx["root_id"],
            "start_ms": ctx["start_ms"],
            "report": ctx["report"],
            **extra,
        }


def _close_root(ctx, attributes=None):
    span_end(
        {
            "trace_id": ctx["trace_id"],
            "span_id": ctx["root_id"],
            "parent_id": None,
            "name": "invoke_agent",
            "agent": "orchestrator",
            "report_id": ctx["report"]["report_id"],
            "start_ms": ctx["start_ms"],
            "status": "OK",
            "attributes": {},
        },
        attributes=attributes or {},
    )


def _fail_closed(ctx, stage_span, denied, stage):
    """An agent the review depends on is not routable. Guessing — approving or rejecting
    without it — would be a decision nobody made, so the report goes to a person.
    This is the same stance as EIR's safety gate, which routes a sensitive action to
    human review when its guardrail is degraded rather than letting it through.
    """
    span_end(
        stage_span,
        status="BLOCKED",
        attributes={
            "denial_reason": denied.reason,
            "summary": f"{stage} agent is not routable ({denied.reason}). Failing closed.",
            "identity": agent_identity.spiffe_id(stage),
        },
    )
    esc = span_start(ctx["trace_id"], uuid.uuid4().hex, ctx["root_id"], "execute_tool", "orchestrator", ctx["report"]["report_id"])
    span_end(
        esc,
        attributes={
            "verdict": "escalated",
            "violations": ["FLEET_DEGRADED"],
            "summary": f"The {stage} agent is unavailable, so this report was not reviewed. Routed to a human instead of guessing.",
        },
    )
    _park("expense", ctx)


def pay_out(ctx):
    """Run (or continue) the payout pipeline for an approved expense: draft, then settle.

    Returns "done" when the payout is finished one way or another, or "parked" when it is
    waiting for a named human to authorize it — in which case the root span stays open
    and a pending entry of kind "payout" exists. Planning goes through
    payouts.plan_capability, so calling this twice for one report cannot pay twice.
    """
    report = ctx["report"]
    rid = report["report_id"]
    token = agent_identity.issue_token("orchestrator")
    identity = agent_identity.spiffe_id("reimbursement")

    if payouts.plan_capability("ExpenseApproved", rid) == "reimbursement.draft":
        span = span_start(ctx["trace_id"], uuid.uuid4().hex, ctx["root_id"], "execute_tool", "reimbursement", rid)
        time.sleep(0.2)
        case = agent_gateway.invoke(token, "reimbursement.draft", report)
        span_end(
            span,
            attributes={
                "payout_id": case["payout_id"],
                "amount_usd": case["amount_usd"],
                "summary": f"Drafted a ${case['amount_usd']:,.2f} payout to {case['payee']}.",
                "identity": identity,
            },
        )

    if payouts.plan_capability("PayoutDrafted", rid) != "reimbursement.settle":
        return "done"

    payout_id = payouts.payout_id_for(rid)
    amount = payouts.get(payout_id)["amount_usd"]
    span = span_start(ctx["trace_id"], uuid.uuid4().hex, ctx["root_id"], "execute_tool", "reimbursement", rid)
    time.sleep(0.2)
    try:
        result = agent_gateway.invoke(token, "reimbursement.settle", payout_id, subject=payout_id)
    except agent_gateway.ApprovalRequired:
        span_end(
            span,
            attributes={
                "awaiting_payout_authorization": True,
                "payout_id": payout_id,
                "amount_usd": amount,
                "summary": (
                    f"${amount:,.2f} is over the ${payouts.AUTHORIZATION_THRESHOLD_USD} authorization line. "
                    "Parked until a named person authorizes it."
                ),
                "identity": identity,
            },
        )
        _park("payout", ctx, payout_id=payout_id)
        return "parked"
    span_end(
        span,
        attributes={
            "payout_status": "paid",
            "payout_id": payout_id,
            "amount_usd": result["amount_usd"],
            "summary": f"Paid ${result['amount_usd']:,.2f} (under the ${payouts.AUTHORIZATION_THRESHOLD_USD} authorization line).",
            "identity": identity,
        },
    )
    return "done"


def orchestrate(report):
    trace_id = uuid.uuid4().hex
    root_id = uuid.uuid4().hex
    report_id = report["report_id"]

    root = span_start(trace_id, root_id, None, "invoke_agent", "orchestrator", report_id)
    ctx = {"trace_id": trace_id, "root_id": root_id, "start_ms": root["start_ms"], "report": report}

    screen_span = span_start(trace_id, uuid.uuid4().hex, root_id, "execute_tool", "screening", report_id)
    time.sleep(0.25)
    # The Orchestrator holds its own identity and asks the gateway for a capability by
    # name — the registry decides who serves it, the token's scopes decide whether the
    # call is allowed. See agent_gateway.py / agent_registry.py / agent_identity.py.
    token = agent_identity.issue_token("orchestrator")
    try:
        violations = agent_gateway.invoke(token, "screening.check_policy", report)
    except agent_gateway.GatewayDenied as denied:
        if denied.reason != "AGENT_UNAVAILABLE":
            raise
        _fail_closed(ctx, screen_span, denied, "screening")
        return
    span_end(
        screen_span,
        attributes={
            "violations": violations,
            "summary": summarize(report, violations),
            "identity": agent_identity.spiffe_id("screening"),
        },
    )

    pii_span = span_start(trace_id, uuid.uuid4().hex, root_id, "execute_tool", "pii_compliance", report_id)
    time.sleep(0.25)
    try:
        result = agent_gateway.invoke(token, "pii_compliance.decide", report, violations)
    except agent_gateway.GatewayDenied as denied:
        if denied.reason != "AGENT_UNAVAILABLE":
            raise
        _fail_closed(ctx, pii_span, denied, "pii_compliance")
        return
    identity = agent_identity.spiffe_id("pii_compliance")

    if result["verdict"] == "blocked":
        span_end(
            pii_span,
            status="BLOCKED",
            attributes={
                "verdict": "blocked",
                "armor_verdict": result["armor_verdict"],
                "summary": result["summary"],
                "identity": identity,
            },
        )
    else:
        span_end(
            pii_span,
            attributes={
                "verdict": result["verdict"],
                "dlp_redactions": result["dlp_redactions"],
                "summary": result["summary"],
                "identity": identity,
            },
        )

    if result["verdict"] == "escalated":
        # Root span deliberately stays open (no span_end here) — it represents the
        # run genuinely parked awaiting a manager, not a fixed sleep. resolve_pending()
        # closes it later, whenever /approve or /deny actually gets called.
        _park("expense", ctx)
        return

    if result["verdict"] == "approved" and pay_out(ctx) == "parked":
        return

    time.sleep(0.05)
    _close_root(ctx)


def resolve_pending(report_id, decision_label, approver=None, reason=None):
    """Resolve whatever this report is parked on. Returns True if something was pending.

    Raises ValueError, *without* consuming the pending entry, when a payout is being
    authorized with no name attached: spending money without knowing who said yes is
    the audit-trail gap docs/REVIEW.md calls disqualifying.
    """
    with pending_lock:
        entry = pending_approvals.get(report_id)
        if entry is None:
            return False
        if entry["kind"] == "payout" and decision_label == "approved" and not (approver and approver.strip()):
            raise ValueError("an approver's name is required to authorize a payout")
        del pending_approvals[report_id]

    ctx = {k: entry[k] for k in ("trace_id", "root_id", "start_ms", "report")}
    attribution = {
        **({"approver": approver} if approver else {}),
        **({"decision_reason": reason} if reason else {}),
    }
    who = approver or "Manager"
    why = f" — {reason}" if reason else ""

    if entry["kind"] == "payout":
        payout_id = entry["payout_id"]
        span = span_start(ctx["trace_id"], uuid.uuid4().hex, ctx["root_id"], "execute_tool", "reimbursement", report_id)
        time.sleep(0.1)
        identity = agent_identity.spiffe_id("reimbursement")
        if decision_label == "approved":
            grant = agent_identity.issue_approval("reimbursement.settle", payout_id, approver, reason)
            token = agent_identity.issue_token("orchestrator")
            result = agent_gateway.invoke(token, "reimbursement.settle", payout_id, approval=grant, subject=payout_id)
            span_end(
                span,
                attributes={
                    "payout_status": "paid",
                    "payout_id": payout_id,
                    "amount_usd": result["amount_usd"],
                    "summary": f"Paid ${result['amount_usd']:,.2f} — authorized by {who}{why}.",
                    "identity": identity,
                    **attribution,
                },
            )
        else:
            payouts.cancel(payout_id)
            span_end(
                span,
                attributes={
                    "payout_status": "cancelled",
                    "payout_id": payout_id,
                    "summary": f"Payout cancelled by {who}{why}.",
                    "identity": identity,
                    **attribution,
                },
            )
        _close_root(ctx, {"manager_decision": decision_label})
        return True

    resume = span_start(ctx["trace_id"], uuid.uuid4().hex, ctx["root_id"], "execute_tool", "orchestrator", report_id)
    time.sleep(0.05)
    span_end(
        resume,
        attributes={
            "manager_decision": decision_label,
            **attribution,
            "summary": f"{who} {decision_label}" + (why if reason else " after review") + ". Run resumed.",
        },
    )
    # An approved expense goes on to be paid — which may park again, on the payout.
    if decision_label == "approved" and pay_out(ctx) == "parked":
        return True
    _close_root(ctx, {"manager_decision": decision_label})
    return True


def run_denied_access_demo(scenario):
    """Streams one gateway attack to the radar. The call is real: a genuine token (or a
    forged/expired one) goes to agent_gateway.invoke(), and the BLOCKED span carries the
    reason the gateway actually returned — not a canned string. The trace contract's
    status enum is OK|BLOCKED|ERROR, so a denial reuses BLOCKED with a denial_reason
    attribute and the radar's existing red-blip handling covers it.
    """
    trace_id = uuid.uuid4().hex
    span_id = uuid.uuid4().hex

    span = span_start(trace_id, span_id, None, "execute_tool", scenario["agent"], scenario["id"])
    time.sleep(0.15)
    denied = security_demos.attempt(scenario)
    if denied is None:
        span_end(span, status="ERROR", attributes={"summary": "Gateway let an unauthorized call through."})
        return
    span_end(
        span,
        status="BLOCKED",
        attributes={
            "denial_reason": denied.reason,
            "claim": scenario["claim"],
            "identity": agent_identity.spiffe_id(scenario["agent"]),
            "summary": f"Agent Gateway refused ({denied.reason}): {denied.caller} -> {denied.capability}. {scenario['claim']}.",
        },
    )


def run_loop():
    reports = load_fixtures()
    if not reports:
        print(f"No fixtures found in {FIXTURES_DIR}")
        return
    i = 0
    cycle = 0
    while True:
        try:
            report = reports[i % len(reports)]
            with pending_lock:
                already_pending = report["report_id"] in pending_approvals
            if not already_pending:
                orchestrate(report)
            if i % len(reports) == 2:
                # One attack per pass, rotating, so the audit trail stays readable.
                scenarios = security_demos.SCENARIOS
                run_denied_access_demo(scenarios[cycle % len(scenarios)])
                cycle += 1
        except Exception as exc:  # noqa: BLE001 - a bad report must not kill the stream
            print(f"[local_server] iteration failed: {exc!r}")
        i += 1
        time.sleep(GAP_BETWEEN_REPORTS_S)


MAX_BODY_BYTES = 20_000
MAX_FIELD_CHARS = 2_000
_manual_ids = itertools.count(1)


class SubmissionError(ValueError):
    pass


def build_manual_report(payload):
    """Turn a submitted form into a report, or raise SubmissionError.

    The report id is assigned here, never accepted from the submitter. Taking it from
    the form would let someone claim an id that already has a receipt on file — the
    id-spoofing hole docs/REVIEW.md reproduces against the real fleet.
    """
    if not isinstance(payload, dict):
        raise SubmissionError("expected a JSON object")

    amount = payload.get("amount_usd")
    if isinstance(amount, bool) or not isinstance(amount, (int, float)) or not 0 < amount <= 1_000_000:
        raise SubmissionError("amount_usd must be a number between 0 and 1,000,000")

    def text(key, required=False):
        value = payload.get(key)
        if value is None or value == "":
            if required:
                raise SubmissionError(f"{key} is required")
            return None
        if not isinstance(value, str):
            raise SubmissionError(f"{key} must be text")
        if len(value) > MAX_FIELD_CHARS:
            raise SubmissionError(f"{key} is longer than {MAX_FIELD_CHARS} characters")
        return value.strip()

    return {
        "report_id": f"EXP-MANUAL-{next(_manual_ids):04d}",
        "submitted_by": "manual_entry",
        "amount_usd": round(float(amount), 2),
        "category": text("category", required=True),
        "merchant": text("merchant"),
        "expense_date": text("expense_date"),
        "description": text("description"),
        "receipt_attached": bool(payload.get("receipt_attached")),
        "receipt_ocr_text": text("receipt_ocr_text"),
        "requested_preapproval": bool(payload.get("requested_preapproval")),
    }


class EventsHandler(BaseHTTPRequestHandler):
    def _json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):
        path, _, query = self.path.partition("?")

        if path == "/submit":
            try:
                length = int(self.headers.get("Content-Length") or 0)
                if length > MAX_BODY_BYTES:
                    raise SubmissionError("request body too large")
                report = build_manual_report(json.loads(self.rfile.read(length) or b"null"))
            except (SubmissionError, ValueError) as err:
                self._json(400, {"ok": False, "error": str(err)})
                return
            # Own thread so the submitter gets an answer now and the review streams to
            # the radar as it happens, independent of the fixture loop.
            threading.Thread(target=orchestrate, args=(report,), daemon=True).start()
            self._json(202, {"ok": True, "report_id": report["report_id"]})
            return

        for prefix, label in (("/approve/", "approved"), ("/deny/", "denied")):
            if path.startswith(prefix):
                params = urllib.parse.parse_qs(query)
                report_id = path[len(prefix):]
                try:
                    resolved = resolve_pending(
                        report_id,
                        label,
                        approver=(params.get("approver") or [None])[0],
                        reason=(params.get("reason") or [None])[0],
                    )
                except ValueError as err:
                    self._json(400, {"ok": False, "error": str(err)})
                    return
                if resolved:
                    self._json(200, {"ok": True, "report_id": report_id, "decision": label})
                else:
                    self._json(404, {"ok": False, "error": f"{report_id} is not pending approval"})
                return

        self._json(404, {"ok": False, "error": "not found"})

    def do_GET(self):
        if self.path == "/events":
            self._stream_events()
            return

        if self.path == "/registry":
            self._json(200, {"agents": agent_registry.list_agents(), "capabilities": agent_registry.list_capabilities()})
            return

        if self.path == "/gateway/audit":
            self._json(200, {"decisions": agent_gateway.audit_log()})
            return

        if self.path == "/pending":
            with pending_lock:
                report_ids = list(pending_approvals.keys())
                kinds = {rid: entry["kind"] for rid, entry in pending_approvals.items()}
            self._json(200, {"pending": report_ids, "kinds": kinds})
            return

        # Approve and deny are POST-only. They change state (and may authorize a
        # payout), and a GET can be fired by a link prefetcher or a crawler.
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
        # Catch a late-joining radar up on anything parked, before live events arrive.
        for frame in backlog_frames():
            q.put_nowait(frame)
        with clients_lock:
            clients.append(q)
        try:
            self.wfile.write(b": connected\n\n")
            while True:
                frame = q.get()
                self.wfile.write(frame.encode("utf-8"))
                self.wfile.flush()
        except OSError:
            pass  # client disconnected (BrokenPipeError, ConnectionAbortedError on Windows, etc.)
        finally:
            with clients_lock:
                if q in clients:
                    clients.remove(q)

    def log_message(self, fmt, *args):
        pass  # keep stdout clean; loop already prints per-report progress if needed


if __name__ == "__main__":
    agents.bootstrap(RULES_PATH)  # provision before the first request, not inside the loop thread
    threading.Thread(target=run_loop, daemon=True).start()
    server = ThreadingHTTPServer(("localhost", PORT), EventsHandler)
    print(f"Local reference /events server on http://localhost:{PORT}/events")
    server.serve_forever()
