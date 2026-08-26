import { useState } from "react";
import RadarCanvas from "./components/RadarCanvas";
import AuditDrawer from "./components/AuditDrawer";
import ScenarioPicker from "./components/ScenarioPicker";
import { useTracePlayer } from "./lib/useTracePlayer";
import { useLiveTraceStream } from "./lib/useLiveTraceStream";
import "./App.css";

const EVENTS_URL = "http://localhost:8000/events";

export default function App() {
  const [mode, setMode] = useState("replay"); // "replay" | "live"
  const mock = useTracePlayer();
  const live = useLiveTraceStream(mode === "live" ? EVENTS_URL : null);

  const feed = mode === "live" ? live : mock;

  return (
    <div className="app">
      <header className="app-header">
        <h1>Agent Radar</h1>
        <p className="app-subtitle">
          Expense Compliance Fleet — live reasoning-chain visualization
        </p>
      </header>

      <div className="mode-row">
        <button
          className={`mode-btn ${mode === "replay" ? "mode-btn--active" : ""}`}
          onClick={() => setMode("replay")}
        >
          Replay (mock)
        </button>
        <button
          className={`mode-btn ${mode === "live" ? "mode-btn--active" : ""}`}
          onClick={() => setMode("live")}
        >
          Live (/events)
        </button>
        {mode === "live" && (
          <span className={`live-status ${live.connected ? "live-status--on" : ""}`}>
            {live.connected ? "connected" : "connecting…"}
          </span>
        )}
      </div>

      {mode === "replay" && <ScenarioPicker onPlay={mock.play} />}

      <main className="app-main">
        <RadarCanvas activeSpans={feed.activeSpans} blip={feed.blip} />
        <AuditDrawer completedSpans={feed.completedSpans} />
      </main>
    </div>
  );
}
