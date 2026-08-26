import { SCENARIOS } from "../mock/scenarios";
import "./ScenarioPicker.css";

// Dev-only control for replaying the five demo scenarios against mock spans.
// Deleted once the SSE client (Day 2) drives the radar from a live backend instead.
export default function ScenarioPicker({ onPlay }) {
  return (
    <div className="scenario-picker">
      <span className="scenario-picker-label">Replay demo scenario:</span>
      {SCENARIOS.map((s) => (
        <button key={s.id} className="scenario-btn" onClick={() => onPlay(s)}>
          {s.label}
        </button>
      ))}
    </div>
  );
}
