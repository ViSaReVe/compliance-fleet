// Helpers that turn a flat list of completed spans into per-report facts. Shared by the
// audit drawer and the persona views so every view agrees on what "awaiting" means.

export function groupByReport(spans) {
  const byReport = new Map();
  for (const s of spans) {
    if (!byReport.has(s.report_id)) byReport.set(s.report_id, []);
    byReport.get(s.report_id).push(s);
  }
  return byReport;
}

export function verdictOf(spans) {
  const withVerdict = spans.find((s) => s.attributes?.verdict);
  return withVerdict?.attributes.verdict ?? (spans.some((s) => s.status === "BLOCKED") ? "blocked" : "pending");
}

// An escalated report is still "awaiting a manager" until a resume span carrying
// manager_decision shows up for it — see backend/devtools/local_server.py resolve_pending().
export function isAwaitingApproval(spans, verdict) {
  if (verdict !== "escalated") return false;
  return !spans.some((s) => s.attributes?.manager_decision);
}

// A payout is its own wait. The expense can be approved while the payout it triggered is
// still parked on a person, so this is read from the payout's own spans, not the verdict.
export function payoutState(spans) {
  if (spans.some((s) => s.attributes?.payout_status === "paid")) return "paid";
  if (spans.some((s) => s.attributes?.payout_status === "cancelled")) return "cancelled";
  if (spans.some((s) => s.attributes?.awaiting_payout_authorization)) return "awaiting";
  return null;
}

// What a person is being asked to decide, if anything: "payout", "expense" or null.
export function awaitingKind(spans) {
  if (payoutState(spans) === "awaiting") return "payout";
  if (isAwaitingApproval(spans, verdictOf(spans))) return "expense";
  return null;
}

export function redactionCount(spans) {
  let n = 0;
  for (const s of spans) {
    const r = s.attributes?.dlp_redactions;
    if (typeof r === "number") n += r;
    else if (Array.isArray(r)) n += r.length;
  }
  return n;
}

export function startedAt(spans) {
  return Math.min(...spans.map((s) => s.start_ms ?? Infinity));
}

export function amountOf(spans) {
  for (const s of spans) {
    const a = s.attributes?.amount_usd;
    if (typeof a === "number") return a;
  }
  return null;
}

export const VERDICT_CLASS = {
  approved: "verdict--approved",
  flagged: "verdict--flagged",
  escalated: "verdict--escalated",
  blocked: "verdict--blocked",
  pending: "verdict--pending",
};

export const PAYOUT_LABEL = { paid: "paid", cancelled: "payout cancelled", awaiting: "payout pending" };
