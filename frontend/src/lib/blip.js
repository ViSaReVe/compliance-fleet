// A BLOCKED span can mean two different things — Model Armor stopping an injection,
// or the Agent Gateway refusing an unauthorized cross-agent call. Both reuse the same
// trace-contract status value, so the label is derived from which attribute is set
// rather than a separate status enum.
export function blipFromSpan(span) {
  if (span.status !== "BLOCKED") return null;
  const label = span.attributes?.armor_verdict
    ? "Model Armor blocked"
    : span.attributes?.denial_reason
      ? "Agent Gateway denied"
      : "Blocked";
  return { agent: span.agent, label, summary: span.attributes?.summary };
}
