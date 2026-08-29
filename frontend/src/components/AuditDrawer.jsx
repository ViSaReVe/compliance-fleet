import { useEffect, useMemo, useRef, useState } from "react";
import "./AuditDrawer.css";

function groupByReport(spans) {
  const byReport = new Map();
  for (const s of spans) {
    if (!byReport.has(s.report_id)) byReport.set(s.report_id, []);
    byReport.get(s.report_id).push(s);
  }
  return byReport;
}

function verdictOf(spans) {
  const withVerdict = spans.find((s) => s.attributes?.verdict);
  return withVerdict?.attributes.verdict ?? (spans.some((s) => s.status === "BLOCKED") ? "blocked" : "pending");
}

// An escalated report is still "awaiting a manager" until a resume span carrying
// manager_decision shows up for it — see backend/devtools/local_server.py resolve_pending().
function isAwaitingApproval(spans, verdict) {
  if (verdict !== "escalated") return false;
  return !spans.some((s) => s.attributes?.manager_decision);
}

import { BACKEND_URL as EVENTS_HOST } from "../lib/config";

// The trace contract types violations as an array, but a backend that ships it as a
// JSON string would otherwise blank the whole drawer mid-demo. Normalise, don't crash.
function violationList(span) {
  const raw = span.attributes?.violations;
  if (Array.isArray(raw)) return raw;
  if (typeof raw === "string") {
    try {
      const parsed = JSON.parse(raw);
      return Array.isArray(parsed) ? parsed : [raw];
    } catch {
      return [raw];
    }
  }
  return [];
}

const VERDICT_CLASS = {
  approved: "verdict--approved",
  flagged: "verdict--flagged",
  escalated: "verdict--escalated",
  blocked: "verdict--blocked",
  pending: "verdict--pending",
};

const VERDICT_HINT = {
  approved: "Within policy, no action needed.",
  flagged: "Policy violation found; needs a closer look.",
  escalated: "Over a threshold with no pre-approval — parked for a manager.",
  blocked: "Model Armor or the Agent Gateway intercepted this before it completed.",
  pending: "Still in progress.",
};

export default function AuditDrawer({ completedSpans, mode }) {
  const [openReport, setOpenReport] = useState(null);
  const [flashId, setFlashId] = useState(null);
  const prevTopIdRef = useRef(null);
  const byReport = useMemo(() => groupByReport(completedSpans), [completedSpans]);
  const reportIds = [...byReport.keys()];

  useEffect(() => {
    const topId = reportIds[0];
    if (topId && topId !== prevTopIdRef.current) {
      prevTopIdRef.current = topId;
      setFlashId(topId);
      const t = setTimeout(() => setFlashId(null), 900);
      return () => clearTimeout(t);
    }
    return undefined;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [completedSpans]);

  const stats = useMemo(() => {
    const counts = { approved: 0, flagged: 0, escalated: 0, blocked: 0 };
    for (const spans of byReport.values()) {
      const v = verdictOf(spans);
      if (v in counts) counts[v] += 1;
    }
    return counts;
  }, [byReport]);

  function resolve(id, decision) {
    fetch(`${EVENTS_HOST}/${decision}/${id}`).catch(() => {});
  }

  return (
    <div className="drawer">
      <h2 className="drawer-title">Audit trail</h2>
      {reportIds.length > 0 && (
        <div className="stats-row">
          <span className="stat stat--approved">{stats.approved} approved</span>
          <span className="stat stat--flagged">{stats.flagged} flagged</span>
          <span className="stat stat--escalated">{stats.escalated} escalated</span>
          <span className="stat stat--blocked">{stats.blocked} blocked</span>
        </div>
      )}
      {reportIds.length === 0 && <p className="drawer-empty">No reports processed yet.</p>}
      <ul className="report-list">
        {reportIds.map((id) => {
          const spans = byReport.get(id);
          const verdict = verdictOf(spans);
          const awaitingApproval = mode === "live" && isAwaitingApproval(spans, verdict);
          const isOpen = openReport === id;
          return (
            <li key={id} className={`report-item ${flashId === id ? "report-item--flash" : ""}`}>
              <button className="report-row" onClick={() => setOpenReport(isOpen ? null : id)}>
                <span className="report-id">{id}</span>
                <span className={`verdict-pill ${VERDICT_CLASS[verdict]}`} title={VERDICT_HINT[verdict]}>
                  {verdict}
                </span>
              </button>
              {awaitingApproval && (
                <div className="approval-row">
                  <span className="approval-label">Awaiting manager…</span>
                  <button className="approve-btn approve-btn--yes" onClick={() => resolve(id, "approve")}>
                    Approve
                  </button>
                  <button className="approve-btn approve-btn--no" onClick={() => resolve(id, "deny")}>
                    Deny
                  </button>
                </div>
              )}
              {isOpen && (
                <ol className="chain">
                  {[...spans].reverse().map((s) => (
                    <li key={s.span_id} className={`chain-step ${s.status === "BLOCKED" ? "chain-step--blocked" : ""}`}>
                      <div className="chain-head">
                        <span className="chain-agent">{s.agent}</span>
                        <span className="chain-name">{s.name}</span>
                      </div>
                      {s.attributes?.summary && <p className="chain-summary">{s.attributes.summary}</p>}
                      {violationList(s).length > 0 && (
                        <p className="chain-violations">{violationList(s).join(", ")}</p>
                      )}
                    </li>
                  ))}
                </ol>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
