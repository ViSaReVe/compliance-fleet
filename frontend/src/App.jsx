import { useState } from "react";
import RadarCanvas from "./components/RadarCanvas";
import AuditDrawer from "./components/AuditDrawer";
import ScenarioPicker from "./components/ScenarioPicker";
import Legend from "./components/Legend";
import { useTracePlayer } from "./lib/useTracePlayer";
import { useLiveTraceStream } from "./lib/useLiveTraceStream";
import { BACKEND_URL } from "./lib/config";
import "./App.css";

const EVENTS_URL = `${BACKEND_URL}/events`;

export default function App() {
  const [mode, setMode] = useState("replay"); // "replay" | "live"
  const mock = useTracePlayer();
  const live = useLiveTraceStream(mode === "live" ? EVENTS_URL : null);

  const feed = mode === "live" ? live : mock;

  return (
    <div className="app">
      <div className="starfield" aria-hidden="true" />
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
          title="Play back one of the 5 demo scenarios on demand, client-side only."
        >
          Replay (mock)
        </button>
        <button
          className={`mode-btn ${mode === "live" ? "mode-btn--active" : ""}`}
          onClick={() => setMode("live")}
          title="Stream real spans from the backend at localhost:8000/events."
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
        <div className="radar-column">
          <RadarCanvas activeSpans={feed.activeSpans} blip={feed.blip} />
          <Legend />
        </div>
        <AuditDrawer completedSpans={feed.completedSpans} mode={mode} />
      </main>
    </div>
  );
}
