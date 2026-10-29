# ADR 0002: The gateway enforces identity, scope, and human approval

## Status

Accepted. Local stand-in only; the managed Agent Gateway is not deployed (see
`COMPLIANCE-MATRIX.md`).

## Context

The first local gateway was a dict of `capability -> {allowed caller names}`, and the caller
supplied its own name. Anything can claim to be "orchestrator", so the allowlist enforced
nothing. It also had no answer for the one case that needs a person: an action that is
permitted but must wait for a human.

## Decision

Every inter-agent call goes through one function, `agent_gateway.invoke`, which checks in
order: the token verifies (signature, expiry, type); the capability exists in the registry;
its owning agent is routable; the token carries the scope the registry requires; and, if the
capability needs a human, a valid approval grant accompanies the call.

Two outcomes are deliberately different:

- **No approval attached** is not an attack. It is the normal "park this for a person" path,
  so it raises `ApprovalRequired` and is audited as such.
- **A bad approval** (forged, expired, for a different capability or payout, replayed, or the
  wrong token type) is an attack and is refused with its own reason.

An approval is a signed grant bound to one capability and one subject and to a *named*
approver, valid for five minutes, and spendable once. Issuing one with no name fails: an
approval trail that cannot say who signed is not a trail.

Access tokens and approval grants share a signing key, so each carries a `typ` and neither
verifies as the other.

An unavailable agent is refused (`AGENT_UNAVAILABLE`) and the orchestrator responds by
routing the report to a human rather than guessing. A degraded agent still takes calls:
degraded is a warning to an operator, unavailable is a refusal.

## Consequences

- Each refusal carries a distinct reason, so the tests assert the *specific* reason, not
  merely that something was refused. A refusal for the wrong reason means a different check
  caught it and the intended one is untested.
- The checks are mutation-tested: bypassing the approval gate, allowing approval reuse, and
  making the ledger non-idempotent each make specific checks fail.
- The approver's name is caller-supplied and unauthenticated. It is recorded and bound into
  the grant, but proving who the approver is would need real authentication.
- This is a design proof, not a deployment. A function is not a managed IAP-enforced
  gateway, and an HMAC token is not an mTLS-bound identity.
