import { useMemo, useState } from "react";
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

const VERDICT_CLASS = {
  approved: "verdict--approved",
  flagged: "verdict--flagged",
  escalated: "verdict--escalated",
  blocked: "verdict--blocked",
  pending: "verdict--pending",
};

export default function AuditDrawer({ completedSpans }) {
  const [openReport, setOpenReport] = useState(null);
  const byReport = useMemo(() => groupByReport(completedSpans), [completedSpans]);
  const reportIds = [...byReport.keys()];

  return (
    <div className="drawer">
      <h2 className="drawer-title">Audit trail</h2>
      {reportIds.length === 0 && <p className="drawer-empty">No reports processed yet.</p>}
      <ul className="report-list">
        {reportIds.map((id) => {
          const spans = byReport.get(id);
          const verdict = verdictOf(spans);
          const isOpen = openReport === id;
          return (
            <li key={id} className="report-item">
              <button className="report-row" onClick={() => setOpenReport(isOpen ? null : id)}>
                <span className="report-id">{id}</span>
                <span className={`verdict-pill ${VERDICT_CLASS[verdict]}`}>{verdict}</span>
              </button>
              {isOpen && (
                <ol className="chain">
                  {[...spans].reverse().map((s) => (
                    <li key={s.span_id} className={`chain-step ${s.status === "BLOCKED" ? "chain-step--blocked" : ""}`}>
                      <div className="chain-head">
                        <span className="chain-agent">{s.agent}</span>
                        <span className="chain-name">{s.name}</span>
                      </div>
                      {s.attributes?.summary && <p className="chain-summary">{s.attributes.summary}</p>}
                      {s.attributes?.violations?.length > 0 && (
                        <p className="chain-violations">{s.attributes.violations.join(", ")}</p>
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
