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
