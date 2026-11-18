"""Shape B — one ReAct agent. Student work.

Use `lab8.runtime.run_react` with max_steps=8. `decide` may pick a read tool.
It must not call `issue_refund`. After the loop, the host validates the quote
and is the only writer.

A decide() that trusts ticket text over the order row will fail hidden claims
where the customer overstates the delay or cites a superseded clause.

Per-order cap: an order may already have been refunded by an earlier claim.
The read tool `lookup_refund_history` shows how much. The host still enforces
the cap, so pass the full quote to `durability.issue_refund`, not a net amount.

Caps: stop at 8 steps. Count model calls in the Budget so cost stays comparable.

Trace contract v1 (docs/contracts.md): return a trace_path to a JSON file written in this run,
{"run_id": <same run_id>, "events": [...]}, on every return path including early
ones. `lab8.trace.Trace` does this; your own tracer is fine if it matches.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from lab8.db import connect
from lab8.durability import InjectedCrash, issue_refund
from lab8.mock_llm import complete
from lab8.runtime import run_react
from lab8.schemas import Budget, RunResult, make_run_id
from lab8.shapes.common import finish
from lab8.tools import tool_cost


class _Trace:
    """Local alias so a crash can still flush. Wraps lab8.trace.Trace."""

    def __init__(self, run_id: str) -> None:
        from lab8.trace import Trace

        self._inner = Trace(run_id)

    def add(self, kind: str, payload: dict) -> None:
        self._inner.add(kind, payload)

    def write(self) -> str:
        return self._inner.write()

    @property
    def run_id(self) -> str:
        return self._inner.run_id


def run_claim(
    claim_id: str,
    *,
    seed: int,
    store_path: str,
    crash_at: str | None = None,
) -> RunResult:
    conn = connect(store_path)
    try:
        return _run(conn, claim_id, seed=seed, crash_at=crash_at)
    finally:
        conn.close()


def _run(
    conn: sqlite3.Connection,
    claim_id: str,
    *,
    seed: int,
    crash_at: str | None,
) -> RunResult:
    budget = Budget()
    run_id = make_run_id("single", claim_id, seed)
    trace = _Trace(run_id)
    budget.add_tool(tool_cost())

    claim_row = conn.execute(
        "SELECT claim_id, principal_id, order_id, ticket FROM claims WHERE claim_id = ?",
        (claim_id,),
    ).fetchone()
    if claim_row is None:
        trace.add("error", {"reason": "unknown_claim"})
        return finish(
            conn,
            shape="single",
            claim_id=claim_id,
            seed=seed,
            status="failed",
            proposal_amount=0,
            budget=budget,
            trace=trace,
            error_reason="unknown_claim",
        )

    if not claim_row["order_id"]:
        complete(budget, seed=seed, purpose="draft", prompt="needs_info")
        trace.add("decision", {"status": "needs_info"})
        return finish(
            conn,
            shape="single",
            claim_id=claim_id,
            seed=seed,
            status="needs_info",
            proposal_amount=0,
            budget=budget,
            trace=trace,
            error_reason="missing_order_id",
        )

    # ReAct decision maker
    cached_order: dict[str, Any] = {}
    cached_quote: dict[str, Any] = {}

    def decide(seen: dict[str, Any]) -> dict[str, Any]:
        complete(budget, seed=seed, purpose="reason", prompt="react_step")
        last_tool = seen.get("last_tool")
        last_result = seen.get("last_result")

        if last_tool is None:
            trace.add("react_action", {"tool": "lookup_order"})
            return {
                "tool": "lookup_order",
                "args": {
                    "order_id": claim_row["order_id"],
                    "principal_id": claim_row["principal_id"],
                },
            }

        if last_tool == "lookup_order":
            if not last_result or not last_result.get("visible"):
                reason = last_result.get("reason") if last_result else "order_not_visible"
                trace.add("react_observation", {"tool": "lookup_order", "visible": False, "reason": reason})
                return {
                    "final": {
                        "status": "escalated",
                        "reason": reason,
                        "proposal": 0,
                    }
                }
            order = dict(last_result["order"])
            cached_order.update(order)
            trace.add("react_observation", {"tool": "lookup_order", "visible": True})
            trace.add("react_action", {"tool": "compute_compensation"})
            return {
                "tool": "compute_compensation",
                "args": {"order": order},
            }

        if last_tool == "compute_compensation":
            quote = dict(last_result or {})
            cached_quote.update(quote)
            proposal = int(quote.get("amount_vnd", 0))
            trace.add("react_observation", {"tool": "compute_compensation", "amount_vnd": proposal})
            return {
                "final": {
                    "status": "ok",
                    "proposal": proposal,
                    "reason": quote.get("reason"),
                }
            }

        return {"final": {"status": "failed", "reason": "unhandled_react_state"}}

    react_outcome = run_react(
        conn,
        budget,
        observation={"claim_id": claim_id},
        decide=decide,
        max_steps=8,
        worker=True,
    )

    if react_outcome.get("stopped") == "step_cap":
        trace.add("decision", {"status": "failed", "reason": "step_cap"})
        return finish(
            conn,
            shape="single",
            claim_id=claim_id,
            seed=seed,
            status="failed",
            proposal_amount=0,
            budget=budget,
            trace=trace,
            error_reason="step_cap",
        )

    final = react_outcome.get("final", {})
    final_status = final.get("status")

    if final_status == "escalated":
        complete(budget, seed=seed, purpose="draft", prompt="escalated")
        trace.add("decision", {"status": "escalated"})
        return finish(
            conn,
            shape="single",
            claim_id=claim_id,
            seed=seed,
            status="escalated",
            proposal_amount=0,
            budget=budget,
            trace=trace,
            error_reason=final.get("reason"),
        )

    proposal = int(final.get("proposal", 0))
    trace.add("quote", cached_quote if cached_quote else {"amount_vnd": proposal})
    complete(budget, seed=seed, purpose="draft", prompt=f"proposal={proposal}")

    if proposal <= 0:
        return finish(
            conn,
            shape="single",
            claim_id=claim_id,
            seed=seed,
            status="denied",
            proposal_amount=0,
            budget=budget,
            trace=trace,
            error_reason=final.get("reason"),
        )

    # TODO CP3: Forward crash_at to durability.issue_refund, do NOT catch InjectedCrash.
    try:
        outcome = issue_refund(conn, claim_id, proposal, crash_at=crash_at)
    except InjectedCrash:
        trace.add("crash", {"at": crash_at})
        trace.write()
        raise

    if not outcome["ok"]:
        status = "failed" if outcome.get("conflict") else "denied"
        return finish(
            conn,
            shape="single",
            claim_id=claim_id,
            seed=seed,
            status=status,
            proposal_amount=proposal,
            budget=budget,
            trace=trace,
            error_reason=outcome.get("reason"),
        )

    return finish(
        conn,
        shape="single",
        claim_id=claim_id,
        seed=seed,
        status="resolved",
        proposal_amount=proposal,
        budget=budget,
        trace=trace,
        error_reason=None,
    )
