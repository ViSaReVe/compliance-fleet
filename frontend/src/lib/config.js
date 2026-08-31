// Backend base URL for both the SSE stream and the approve/deny calls.
//
// Defaults to the local backend, which is either of two interchangeable servers on
// the same port and paths:
//   backend/devtools/local_server.py  zero GCP, zero dependencies, bare python3
//   backend/fleet/server.py           the real fleet, real Model Armor + Cloud DLP
//
// Override in frontend/.env.local to point at a deployed backend instead:
//   VITE_BACKEND_URL=https://your-backend.run.app
export const BACKEND_URL = (
  import.meta.env.VITE_BACKEND_URL || "http://localhost:8000"
).replace(/\/$/, "");

// A hosted build has no backend to stream from — the fleet runs on the recorder's
// machine, not next to the static files. Offering a Live toggle there just lets a
// judge click into a dead "connecting…" state, so the build hides it.
// Set VITE_DEMO_ONLY=1 when building for hosting.
export const DEMO_ONLY = import.meta.env.VITE_DEMO_ONLY === "1";
