"""Human-in-the-loop escalation, using ADK's own pause/resume rather than a
hand-rolled state machine.

When this tool calls tool_context.request_confirmation(), the ADK runner parks the
run and hands control back to the caller. The session lives in Memory Bank, so the
pause survives process restarts — and Agent Runtime supports runs up to seven days,
which is what makes "waiting on a manager who is on PTO" a real capability rather
than a sleep() in a demo script.

Resuming is a fresh run carrying a FunctionResponse, not a message on the original
request queue.
"""

from google.adk.tools import LongRunningFunctionTool, ToolContext


def request_manager_approval(
    report_id: str,
    amount_usd: float,
    violations: str,
    tool_context: ToolContext,
) -> dict:
    """Escalate an expense report to a human manager and wait for their decision.

    Args:
        report_id: Identifier of the expense report being escalated.
        amount_usd: Claimed amount, so the manager sees it without a lookup.
        violations: Comma-separated policy violation codes that triggered escalation.

    Returns:
        The manager's decision once supplied.
    """
    tool_context.request_confirmation(
        hint=(
            f"Expense report {report_id} for ${amount_usd:,.0f} triggered "
            f"{violations or 'policy escalation'} and needs manager sign-off."
        )
    )
    # Execution stops here. The runner resumes this call with the manager's response
    # once a FunctionResponse arrives, and the return value below is what the agent
    # sees at that point.
    return {"report_id": report_id, "status": "awaiting_manager_decision"}


manager_approval_tool = LongRunningFunctionTool(func=request_manager_approval)
