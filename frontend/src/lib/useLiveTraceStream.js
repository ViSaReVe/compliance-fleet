import { useEffect, useRef, useState } from "react";
import { blipFromSpan } from "./blip";

// Consumes the real /events SSE stream (README Setup step 3 — backend/fleet/telemetry.py).
// Same return shape as useTracePlayer.js so RadarCanvas/AuditDrawer don't care which
// hook is feeding them. Event framing: "span_start" (end_ms null, fired when a span
// opens, for the pulse) and "span_end" (full span, for the audit trail) — this framing
// is not yet confirmed with the backend, sync with telemetry.py once it exists.
export function useLiveTraceStream(url) {
  const [connected, setConnected] = useState(false);
  const [activeSpans, setActiveSpans] = useState([]);
  const [completedSpans, setCompletedSpans] = useState([]);
  const [blip, setBlip] = useState(null);
  const sourceRef = useRef(null);

  useEffect(() => {
    if (!url) return undefined;

    const source = new EventSource(url);
    sourceRef.current = source;

    source.onopen = () => setConnected(true);
    source.onerror = () => setConnected(false);

    source.addEventListener("span_start", (e) => {
      const span = JSON.parse(e.data);
      setActiveSpans((prev) => [...prev, span]);
    });

    source.addEventListener("span_end", (e) => {
      const span = JSON.parse(e.data);
      setActiveSpans((prev) => prev.filter((a) => a.span_id !== span.span_id));
      setCompletedSpans((prev) => [span, ...prev]);
      const blip = blipFromSpan(span);
      if (blip) {
        setBlip(blip);
        setTimeout(() => setBlip(null), 1600);
      }
    });

    return () => {
      source.close();
      setConnected(false);
    };
  }, [url]);

  return { connected, activeSpans, completedSpans, blip };
}
