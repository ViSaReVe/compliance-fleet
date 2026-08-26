// Stand-in for backend/fleet/telemetry.py's SSE fan-out (README "Setup" step 3 —
// serves /events on :8000). Lets the radar's live SSE path get built and proven before
// the real ADK SpanProcessor exists. Delete this whole devtools/ folder once
// telemetry.py lands — the frontend contract (event names + span JSON) is written to
// match what that file is expected to emit, so useLiveTraceStream.js won't need to change.
//
// Run: node devtools/mock-events-server.mjs

import { createServer } from "node:http";
import { SCENARIOS } from "../src/mock/scenarios.js";

const PORT = 8000;
const GAP_BETWEEN_SCENARIOS_MS = 2000;

const clients = new Set();

function broadcast(eventName, payload) {
  const frame = `event: ${eventName}\ndata: ${JSON.stringify(payload)}\n\n`;
  for (const res of clients) res.write(frame);
}

function scheduleScenario(scenario) {
  const timers = [];
  for (const s of scenario.spans) {
    timers.push(setTimeout(() => broadcast("span_start", { ...s, end_ms: null }), s.start_ms));
    timers.push(setTimeout(() => broadcast("span_end", s), s.end_ms));
  }
  const last = Math.max(...scenario.spans.map((s) => s.end_ms));
  return last;
}

function runLoop() {
  let idx = 0;
  function step() {
    const scenario = SCENARIOS[idx % SCENARIOS.length];
    idx += 1;
    const duration = scheduleScenario(scenario);
    setTimeout(step, duration + GAP_BETWEEN_SCENARIOS_MS);
  }
  step();
}

const server = createServer((req, res) => {
  if (req.url !== "/events") {
    res.writeHead(404).end();
    return;
  }
  res.writeHead(200, {
    "Content-Type": "text/event-stream",
    "Cache-Control": "no-cache",
    Connection: "keep-alive",
    "Access-Control-Allow-Origin": "*",
  });
  res.write(": connected\n\n");
  clients.add(res);
  req.on("close", () => clients.delete(res));
});

server.listen(PORT, () => {
  console.log(`Mock /events SSE server on http://localhost:${PORT}/events`);
  runLoop();
});
