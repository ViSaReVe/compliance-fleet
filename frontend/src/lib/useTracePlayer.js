import { useCallback, useRef, useState } from "react";

// Plays a scenario's spans back on real relative timing via setTimeout, exactly the
// shape a Day-2 SSE client will produce from the live /events stream: span-start and
// span-end events. Swapping the source later means replacing `play()` with an
// EventSource listener — the consumer (RadarCanvas, AuditDrawer) doesn't change.
export function useTracePlayer() {
  const [activeSpans, setActiveSpans] = useState([]); // spans currently in flight
  const [completedSpans, setCompletedSpans] = useState([]); // full history, newest first
  const [blip, setBlip] = useState(null); // { agent, summary } transient red flag
  const timers = useRef([]);

  const reset = useCallback(() => {
    timers.current.forEach(clearTimeout);
    timers.current = [];
    setActiveSpans([]);
    setBlip(null);
  }, []);

  const play = useCallback(
    (scenario) => {
      reset();
      scenario.spans.forEach((s) => {
        const startTimer = setTimeout(() => {
          setActiveSpans((prev) => [...prev, s]);
        }, s.start_ms);

        const endTimer = setTimeout(() => {
          setActiveSpans((prev) => prev.filter((a) => a.span_id !== s.span_id));
          setCompletedSpans((prev) => [s, ...prev]);
          if (s.status === "BLOCKED") {
            setBlip({ agent: s.agent, summary: s.attributes?.summary });
            setTimeout(() => setBlip(null), 1600);
          }
        }, s.end_ms);

        timers.current.push(startTimer, endTimer);
      });
    },
    [reset]
  );

  return { activeSpans, completedSpans, blip, play, reset };
}
