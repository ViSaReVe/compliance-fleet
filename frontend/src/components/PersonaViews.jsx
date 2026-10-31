import { useEffect, useMemo, useState } from "react";
import { BACKEND_URL } from "../lib/config";
import {
  groupByReport,
  verdictOf,
  payoutState,
  awaitingKind,
  redactionCount,
  startedAt,
  VERDICT_CLASS,
  PAYOUT_LABEL,
} from "../lib/reports";
import SubmitExpense from "./SubmitExpense";
import "./PersonaViews.css";

export const PERSONAS = [
  { id: "overview", label: "Overview", blurb: "Everything on one page." },
  { id: "employee", label: "Employee", blurb: "Submit an expense and follow only your own." },
  { id: "reviewer", label: "Reviewer", blurb: "The queue of things waiting on a person." },
  { id: "ops", label: "Finance ops", blurb: "The fleet's health and what the gateway refused." },
];

export function PersonaBar({ persona, onChange }) {
  const current = PERSONAS.find((p) => p.id === persona);
  return (
    <div className="persona-bar">
      <div className="persona-tabs" role="tablist" aria-label="Demo view">
        {PERSONAS.map((p) => (
          <button
            key={p.id}
            role="tab"
            aria-selected={persona === p.id}
            className={`persona-tab ${persona === p.id ? "persona-tab--active" : ""}`}
            onClick={() => onChange(p.id)}
          >
            {p.label}
          </button>
        ))}
      </div>
      <p className="persona-note">
        <strong>Demo view switch, not a sign-in.</strong> {current.blurb} Nothing here is restricted:
        the backend does not know who you are, and the approver name is typed, not verified.
      </p>
    </div>
  );
}

function StatusLine({ spans }) {
  const verdict = verdictOf(spans);
  const payout = payoutState(spans);
  const waiting = awaitingKind(spans);
  const text = waiting === "payout"
    ? "Approved by policy. The payout is waiting for a person to authorize it."
    : waiting === "expense"
      ? "Over a limit with no pre-approval. Waiting for a manager."
      : { approved: "Within policy.", flagged: "Flagged for a closer look.", blocked: "Stopped by a safety check.", pending: "Being reviewed by the fleet…", escalated: "A manager decided on this." }[verdict];
  return (
    <>
      <span className="pills">
        <span className={`verdict-pill ${VERDICT_CLASS[verdict]}`}>{verdict}</span>
        {payout && <span className={`payout-pill payout-pill--${payout}`}>{PAYOUT_LABEL[payout]}</span>}
      </span>
      <p className="pv-status">{text}</p>
    </>
  );
}

// Ownership here is the browser's: it remembers the ids the backend handed back for
// this session's submissions. The backend itself does not record who submitted what.
export function EmployeeView({ completedSpans, myIds, onSubmitted }) {
  const byReport = useMemo(() => groupByReport(completedSpans), [completedSpans]);
  return (
    <div className="pv-col">
      <SubmitExpense defaultOpen onSubmitted={onSubmitted} />
      <section className="pv-card">
        <h2 className="pv-title">My expenses</h2>
        {myIds.length === 0 && <p className="pv-empty">Nothing submitted in this session yet.</p>}
        <ul className="pv-list">
          {[...myIds].reverse().map((id) => {
            const spans = byReport.get(id);
            return (
              <li key={id} className="pv-item">
                <span className="report-id">{id}</span>
                {spans ? <StatusLine spans={spans} /> : <p className="pv-status">Waiting for the fleet to pick it up…</p>}
              </li>
            );
          })}
        </ul>
      </section>
    </div>
  );
}

function age(ms) {
  const s = Math.max(0, Math.round((Date.now() - ms) / 1000));
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  return m < 60 ? `${m}m` : `${Math.floor(m / 60)}h ${m % 60}m`;
}

export function ReviewerView({ completedSpans }) {
  const [, tick] = useState(0);
  useEffect(() => {
    const t = setInterval(() => tick((n) => n + 1), 1000);
    return () => clearInterval(t);
  }, []);

  const [signing, setSigning] = useState(null); // { id, decision }
  const [approver, setApprover] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState(null);

  const queue = useMemo(() => {
    const out = [];
    for (const [id, spans] of groupByReport(completedSpans)) {
      const kind = awaitingKind(spans);
      if (!kind) continue;
      const summary = [...spans].reverse().find((s) => s.attributes?.summary)?.attributes.summary;
      out.push({ id, kind, since: startedAt(spans), redactions: redactionCount(spans), summary });
    }
    return out.sort((a, b) => a.since - b.since); // oldest first
  }, [completedSpans]);

  async function decide() {
    if (!signing || !approver.trim()) return;
    const query = new URLSearchParams({ approver, reason }).toString();
    try {
      const res = await fetch(`${BACKEND_URL}/${signing.decision}/${signing.id}?${query}`, { method: "POST" });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        setError(body.error || `Rejected (${res.status}).`);
        return;
      }
      setError(null);
      setSigning(null);
      setReason("");
    } catch {
      setError("Could not reach the backend.");
    }
  }

  return (
    <section className="pv-card">
      <h2 className="pv-title">Waiting on a person <span className="pv-count">{queue.length}</span></h2>
      {queue.length === 0 && <p className="pv-empty">Nothing is waiting. Submit an expense over $500 to see one arrive.</p>}
      <ul className="pv-list">
        {queue.map((q) => (
          <li key={q.id} className="pv-item">
            <div className="pv-item-head">
              <span className="report-id">{q.id}</span>
              <span className="pv-age">waiting {age(q.since)}</span>
            </div>
            <p className="pv-status">
              {q.kind === "payout" ? "Payout over $500: needs your authorization." : "Escalated: needs a manager decision."}
            </p>
            {q.summary && <p className="pv-summary">{q.summary}</p>}
            <p className="pv-redact">
              {q.redactions > 0
                ? `${q.redactions} sensitive value${q.redactions === 1 ? "" : "s"} redacted before this reached you.`
                : "No sensitive values were found in this report."}
            </p>
            {signing?.id === q.id ? (
              <div className="pv-sign">
                <input className="approval-input" autoFocus placeholder="Your name" value={approver} onChange={(e) => setApprover(e.target.value)} onKeyDown={(e) => e.key === "Enter" && decide()} />
                <input className="approval-input" placeholder="Reason (optional)" value={reason} onChange={(e) => setReason(e.target.value)} onKeyDown={(e) => e.key === "Enter" && decide()} />
                {error && <span className="submit-msg submit-msg--err">{error}</span>}
                <div className="approval-row">
                  <button className="approve-btn approve-btn--yes" disabled={!approver.trim()} onClick={decide}>
                    Confirm {signing.decision}
                  </button>
                  <button className="approve-btn" onClick={() => { setSigning(null); setError(null); }}>Cancel</button>
                </div>
              </div>
            ) : (
              <div className="approval-row">
                <button className="approve-btn approve-btn--yes" onClick={() => setSigning({ id: q.id, decision: "approve" })}>
                  {q.kind === "payout" ? "Authorize" : "Approve"}
                </button>
                <button className="approve-btn approve-btn--no" onClick={() => setSigning({ id: q.id, decision: "deny" })}>Deny</button>
              </div>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

function usePolled(path, ms = 3000) {
  const [data, setData] = useState(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let alive = true;
    const load = () =>
      fetch(`${BACKEND_URL}${path}`)
        .then((r) => (r.ok ? r.json() : Promise.reject()))
        .then((d) => alive && (setData(d), setFailed(false)))
        .catch(() => alive && setFailed(true));
    load();
    const t = setInterval(load, ms);
    return () => { alive = false; clearInterval(t); };
  }, [path, ms]);
  return { data, failed };
}

const RISK_CLASS = { LOW: "risk--low", MEDIUM: "risk--medium", HIGH: "risk--high", CRITICAL: "risk--critical" };

export function OpsPanels() {
  const registry = usePolled("/registry", 5000);
  const audit = usePolled("/gateway/audit", 2000);
  const agents = registry.data?.agents ?? [];
  const caps = registry.data?.capabilities ?? [];
  const decisions = [...(audit.data?.decisions ?? [])].reverse().slice(0, 12);

  return (
    <>
      <section className="pv-card">
        <h2 className="pv-title">Agent registry</h2>
        {registry.failed && <p className="pv-empty">This backend does not expose /registry.</p>}
        <ul className="pv-list">
          {agents.map((a) => (
            <li key={a.name} className="pv-item">
              <div className="pv-item-head">
                <span className="report-id">{a.name}</span>
                <span className={`risk ${RISK_CLASS[a.risk_level] ?? ""}`}>{a.risk_level}</span>
              </div>
              <p className="pv-status">{a.health ?? "unknown"} · {a.lifecycle ?? "—"}{a.fallback_agent ? ` · falls back to ${a.fallback_agent}` : ""}</p>
              <p className="pv-summary">{caps.filter((c) => c.owner === a.name).map((c) => c.capability + (c.human_approval ? " (human approval)" : "")).join(", ") || "no capabilities"}</p>
            </li>
          ))}
        </ul>
      </section>
      <section className="pv-card">
        <h2 className="pv-title">Gateway decisions <span className="pv-count">{decisions.length}</span></h2>
        {audit.failed && <p className="pv-empty">This backend does not expose /gateway/audit.</p>}
        <ul className="pv-list">
          {decisions.map((d, i) => (
            <li key={`${d.ts_ms}-${i}`} className="pv-item pv-item--tight">
              <span className={`gw ${d.allowed ? "gw--ok" : d.reason === "APPROVAL_REQUIRED" ? "gw--wait" : "gw--no"}`}>
                {d.allowed ? "allowed" : d.reason === "APPROVAL_REQUIRED" ? "parked" : "refused"}
              </span>
              <span className="pv-gw-text">
                {d.caller} → {d.capability}
                {!d.allowed && <em> {d.reason}</em>}
                {d.approver && <em> approved by {d.approver}</em>}
              </span>
            </li>
          ))}
        </ul>
        <p className="pv-footnote">
          Evidence and gaps for every claim: <code>docs/COMPLIANCE-MATRIX.md</code>.
        </p>
      </section>
    </>
  );
}
