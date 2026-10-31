import { useState } from "react";
import RadarCanvas from "./components/RadarCanvas";
import AuditDrawer from "./components/AuditDrawer";
import ScenarioPicker from "./components/ScenarioPicker";
import Legend from "./components/Legend";
import SubmitExpense from "./components/SubmitExpense";
import { PersonaBar, EmployeeView, ReviewerView, OpsPanels } from "./components/PersonaViews";
import { useTracePlayer } from "./lib/useTracePlayer";
import { useLiveTraceStream } from "./lib/useLiveTraceStream";
import { BACKEND_URL, DEMO_ONLY } from "./lib/config";
import "./App.css";

const EVENTS_URL = `${BACKEND_URL}/events`;

export default function App() {
  const [mode, setMode] = useState("replay"); // "replay" | "live"
  const [persona, setPersona] = useState("overview");
  const [myIds, setMyIds] = useState([]);
  const mock = useTracePlayer();
  const live = useLiveTraceStream(mode === "live" ? EVENTS_URL : null);

  const feed = mode === "live" ? live : mock;
  // Personas need the live backend (submit, queue, registry); replay keeps the plain layout.
  const personas = mode === "live" && !DEMO_ONLY;
  const view = personas ? persona : "overview";

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
        {!DEMO_ONLY && (
          <button
            className={`mode-btn ${mode === "live" ? "mode-btn--active" : ""}`}
            onClick={() => setMode("live")}
            title="Stream real spans from the backend at localhost:8000/events."
          >
            Live (/events)
          </button>
        )}
        {DEMO_ONLY && (
          <span className="mode-note">
            Replaying recorded scenarios. The live feed streams from the fleet running
            against Agent Runtime — see the demo video.
          </span>
        )}
        {mode === "live" && (
          <span className={`live-status ${live.connected ? "live-status--on" : ""}`}>
            {live.connected ? "connected" : "connecting…"}
          </span>
        )}
      </div>

      {mode === "replay" && <ScenarioPicker onPlay={mock.play} />}
      {personas && <PersonaBar persona={persona} onChange={setPersona} />}

      {view === "employee" && (
        <main className="app-main app-main--single">
          <EmployeeView
            completedSpans={feed.completedSpans}
            myIds={myIds}
            onSubmitted={(id) => setMyIds((ids) => [...ids, id])}
          />
        </main>
      )}

      {view === "reviewer" && (
        <main className="app-main app-main--single">
          <ReviewerView completedSpans={feed.completedSpans} />
        </main>
      )}

      {(view === "overview" || view === "ops") && (
        <main className="app-main">
          <div className="radar-column">
            <RadarCanvas activeSpans={feed.activeSpans} blip={feed.blip} />
            <Legend />
          </div>
          <div className="side-column">
            {view === "overview" && personas && <SubmitExpense />}
            {view === "ops" && <OpsPanels />}
            <AuditDrawer completedSpans={feed.completedSpans} mode={mode} />
          </div>
        </main>
      )}
    </div>
  );
}
