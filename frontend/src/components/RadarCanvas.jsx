import { AGENT_IDS } from "../mock/scenarios";
import "./RadarCanvas.css";

const NODES = {
  [AGENT_IDS.ORCH]: {
    x: 300,
    y: 90,
    label: "Orchestrator",
    role: "Resolves agents via the Registry, sequences the workflow, tracks per-report state in Memory Bank.",
  },
  [AGENT_IDS.SCREEN]: {
    x: 120,
    y: 460,
    label: "Screening",
    role: "Extracts amount, category, date, and receipt status; checks the report against policy rules.",
  },
  [AGENT_IDS.PII]: {
    x: 480,
    y: 460,
    label: "PII / Compliance",
    role: "Model Armor screens for injection; Cloud DLP redacts PII; issues the final verdict.",
  },
};

function activeAgents(activeSpans) {
  return new Set(activeSpans.map((s) => s.agent));
}

// An "edge" is in-flight when a child span's agent differs from its parent's agent —
// i.e. the orchestrator has handed control to a sub-agent and is waiting on it.
// When the driving span already carries both timestamps (mock replay, where the full
// span is known up front), the sweep-dot travel time is set to the span's *actual*
// duration rather than a fixed loop — matching the "not fake timings" design note.
// A live span_start (end_ms not yet known, since it genuinely hasn't happened) falls
// back to a neutral in-flight speed; its pulse on/off is still gated by the real
// span_start/span_end events regardless.
function activeEdges(activeSpans) {
  const byId = new Map(activeSpans.map((s) => [s.span_id, s]));
  const edges = [];
  for (const s of activeSpans) {
    if (!s.parent_id) continue;
    const parent = byId.get(s.parent_id);
    const parentAgent = parent ? parent.agent : AGENT_IDS.ORCH;
    if (parentAgent !== s.agent && NODES[parentAgent] && NODES[s.agent]) {
      const knownDuration = s.end_ms != null ? s.end_ms - s.start_ms : null;
      edges.push({ from: parentAgent, to: s.agent, key: s.span_id, durationMs: knownDuration });
    }
  }
  return edges;
}

const FALLBACK_EDGE_DUR_S = 0.5;

function edgeDurationSeconds(durationMs) {
  if (durationMs == null) return FALLBACK_EDGE_DUR_S;
  return Math.min(Math.max(durationMs, 150), 3000) / 1000;
}

function currentReportId(activeSpans) {
  const withReport = activeSpans.find((s) => s.report_id);
  return withReport?.report_id ?? null;
}

export default function RadarCanvas({ activeSpans, blip }) {
  const active = activeAgents(activeSpans);
  const edges = activeEdges(activeSpans);
  const reportId = currentReportId(activeSpans);

  return (
    <div className="radar-wrap">
      <svg viewBox="0 0 600 560" className="radar-svg">
        <circle cx="300" cy="300" r="260" className="ring" />
        <circle cx="300" cy="300" r="175" className="ring" />
        <circle cx="300" cy="300" r="90" className="ring" />
        <g className="sweep-group">
          {[24, 18, 12, 6].map((deg) => (
            <line
              key={deg}
              x1="300"
              y1="300"
              x2="300"
              y2="40"
              className="sweep-trail"
              style={{ opacity: 0.5 - deg / 48 }}
              transform={`rotate(-${deg} 300 300)`}
            />
          ))}
          <line x1="300" y1="300" x2="300" y2="40" className="sweep-line" />
        </g>

        <text x="300" y="296" textAnchor="middle" className="scan-label">
          {reportId ? "PROCESSING" : "SCANNING"}
        </text>
        <text x="300" y="316" textAnchor="middle" className="scan-report-id">
          {reportId ?? "—"}
        </text>

        {edges.map((e) => {
          const from = NODES[e.from];
          const to = NODES[e.to];
          return (
            <g key={e.key}>
              <line x1={from.x} y1={from.y} x2={to.x} y2={to.y} className="edge-line" />
              <circle r="6" className="edge-dot">
                <animateMotion
                  dur={`${edgeDurationSeconds(e.durationMs)}s`}
                  repeatCount="indefinite"
                  path={`M${from.x},${from.y} L${to.x},${to.y}`}
                />
              </circle>
            </g>
          );
        })}

        {Object.entries(NODES).map(([agent, node]) => {
          const isActive = active.has(agent);
          const isBlipping = blip?.agent === agent;
          return (
            <g key={agent} transform={`translate(${node.x}, ${node.y})`} className="node-group">
              <title>{`${node.label} — ${node.role}`}</title>
              {isActive && <circle r="34" className="node-pulse" />}
              {isBlipping && <circle r="46" className="node-blip" />}
              <circle
                r="26"
                className={`node-dot ${isActive ? "node-dot--active" : ""} ${
                  isBlipping ? "node-dot--blip" : ""
                }`}
              />
              <text y="48" textAnchor="middle" className="node-label">
                {node.label}
              </text>
              <text y="64" textAnchor="middle" className={`node-status ${isActive ? "node-status--active" : ""}`}>
                {isActive ? "active" : "idle"}
              </text>
            </g>
          );
        })}
      </svg>

      {blip && (
        <div className="toast toast--blip">
          {blip.label}: {blip.summary}
        </div>
      )}
    </div>
  );
}
