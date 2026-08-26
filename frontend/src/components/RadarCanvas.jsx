import { AGENT_IDS } from "../mock/scenarios";
import "./RadarCanvas.css";

const NODES = {
  [AGENT_IDS.ORCH]: { x: 300, y: 90, label: "Orchestrator" },
  [AGENT_IDS.SCREEN]: { x: 120, y: 460, label: "Screening" },
  [AGENT_IDS.PII]: { x: 480, y: 460, label: "PII / Compliance" },
};

function activeAgents(activeSpans) {
  return new Set(activeSpans.map((s) => s.agent));
}

// An "edge" is in-flight when a child span's agent differs from its parent's agent —
// i.e. the orchestrator has handed control to a sub-agent and is waiting on it.
function activeEdges(activeSpans) {
  const byId = new Map(activeSpans.map((s) => [s.span_id, s]));
  const edges = [];
  for (const s of activeSpans) {
    if (!s.parent_id) continue;
    const parent = byId.get(s.parent_id);
    const parentAgent = parent ? parent.agent : AGENT_IDS.ORCH;
    if (parentAgent !== s.agent && NODES[parentAgent] && NODES[s.agent]) {
      edges.push({ from: parentAgent, to: s.agent, key: s.span_id });
    }
  }
  return edges;
}

export default function RadarCanvas({ activeSpans, blip }) {
  const active = activeAgents(activeSpans);
  const edges = activeEdges(activeSpans);

  return (
    <div className="radar-wrap">
      <svg viewBox="0 0 600 560" className="radar-svg">
        <circle cx="300" cy="300" r="260" className="ring" />
        <circle cx="300" cy="300" r="175" className="ring" />
        <circle cx="300" cy="300" r="90" className="ring" />
        <g className="sweep-group">
          <line x1="300" y1="300" x2="300" y2="40" className="sweep-line" />
        </g>

        {edges.map((e) => {
          const from = NODES[e.from];
          const to = NODES[e.to];
          return (
            <g key={e.key}>
              <line x1={from.x} y1={from.y} x2={to.x} y2={to.y} className="edge-line" />
              <circle r="6" className="edge-dot">
                <animateMotion
                  dur="0.5s"
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
            <g key={agent} transform={`translate(${node.x}, ${node.y})`}>
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
            </g>
          );
        })}
      </svg>

      {blip && (
        <div className="toast toast--blip">
          Model Armor blocked: {blip.summary}
        </div>
      )}
    </div>
  );
}
