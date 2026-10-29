import { useState } from "react";
import { BACKEND_URL } from "../lib/config";
import "./SubmitExpense.css";

const CATEGORIES = ["meals", "travel", "lodging", "offsite", "supplies", "software"];

const EMPTY = {
  amount: "",
  category: "meals",
  merchant: "",
  description: "",
  receipt_attached: false,
  requested_preapproval: false,
};

// Manual entry, so the radar can be driven by an expense you typed rather than only a
// looping fixture. The report id is deliberately not a field: the backend assigns it.
// A submitter-chosen id would let someone claim one that already has a receipt on file
// (the id-spoofing hole docs/REVIEW.md reproduces against the real fleet).
export default function SubmitExpense() {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(EMPTY);
  const [state, setState] = useState({ kind: "idle" }); // idle | sending | ok | error

  const set = (key) => (e) =>
    setForm((f) => ({ ...f, [key]: e.target.type === "checkbox" ? e.target.checked : e.target.value }));

  const amount = Number(form.amount);
  const valid = form.amount !== "" && Number.isFinite(amount) && amount > 0;

  async function submit(e) {
    e.preventDefault();
    if (!valid || state.kind === "sending") return;
    setState({ kind: "sending" });
    try {
      const res = await fetch(`${BACKEND_URL}/submit`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          amount_usd: amount,
          category: form.category,
          merchant: form.merchant,
          description: form.description,
          receipt_attached: form.receipt_attached,
          requested_preapproval: form.requested_preapproval,
        }),
      });
      const body = await res.json().catch(() => ({}));
      if (res.ok) {
        setState({ kind: "ok", reportId: body.report_id });
        setForm(EMPTY);
      } else if (res.status === 404) {
        setState({ kind: "error", message: "This backend does not accept manual submissions." });
      } else {
        setState({ kind: "error", message: body.error || `Rejected (${res.status}).` });
      }
    } catch {
      setState({ kind: "error", message: "Could not reach the backend." });
    }
  }

  return (
    <div className="submit">
      <button className="submit-toggle" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        <span>{open ? "−" : "+"} Submit an expense</span>
        <span className="submit-hint">watch it move through the fleet</span>
      </button>

      {open && (
        <form className="submit-form" onSubmit={submit}>
          <div className="submit-row">
            <label className="submit-field submit-field--amount">
              <span>Amount (USD)</span>
              <input
                type="number"
                min="0.01"
                step="0.01"
                inputMode="decimal"
                placeholder="840.00"
                value={form.amount}
                onChange={set("amount")}
              />
            </label>
            <label className="submit-field">
              <span>Category</span>
              <select value={form.category} onChange={set("category")}>
                {CATEGORIES.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <label className="submit-field">
            <span>Merchant</span>
            <input value={form.merchant} onChange={set("merchant")} maxLength={200} placeholder="Riverside Inn" />
          </label>

          <label className="submit-field">
            <span>Description</span>
            <textarea
              rows={2}
              value={form.description}
              onChange={set("description")}
              maxLength={2000}
              placeholder="Client conference hotel stay, two nights."
            />
          </label>

          <div className="submit-checks">
            <label>
              <input type="checkbox" checked={form.receipt_attached} onChange={set("receipt_attached")} /> Receipt attached
            </label>
            <label>
              <input type="checkbox" checked={form.requested_preapproval} onChange={set("requested_preapproval")} />{" "}
              Pre-approval obtained
            </label>
          </div>

          <div className="submit-actions">
            <button type="submit" className="submit-btn" disabled={!valid || state.kind === "sending"}>
              {state.kind === "sending" ? "Submitting…" : "Submit"}
            </button>
            {state.kind === "ok" && <span className="submit-msg submit-msg--ok">Sent as {state.reportId}</span>}
            {state.kind === "error" && <span className="submit-msg submit-msg--err">{state.message}</span>}
          </div>
        </form>
      )}
    </div>
  );
}
