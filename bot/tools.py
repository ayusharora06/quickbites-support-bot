"""Tool schemas + dispatch for the Claude tool-use loop.

Two kinds of tools:
- LOOKUP_TOOLS: pure reads from the DB or policy; results fed back to the model
- ACTION_TOOLS: the 5 simulator actions + a `reply` terminator. The agent loop
  collects these in a list and treats `reply` as the signal to stop.

Action validation lives here too so a hallucinated refund can't slip through.
"""

from __future__ import annotations

import json
from typing import Any

from . import data, policy

# ---------------------------------------------------------------------------
# Tool schemas (Anthropic tool-use format)
# ---------------------------------------------------------------------------

LOOKUP_TOOLS: list[dict[str, Any]] = [
    {
        "name": "get_order",
        "description": (
            "Fetch full detail of an order by id: the order header, items, "
            "restaurant, rider, plus any pre-existing complaints, refunds, "
            "reviews and rider incidents on this same order. Always call this "
            "as soon as the customer gives you an order id."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"order_id": {"type": "integer"}},
            "required": ["order_id"],
        },
    },
    {
        "name": "get_customer_history",
        "description": (
            "Customer profile + lifetime stats + abuse signals. Use this on "
            "the customer behind the order before deciding any refund. The "
            "`yellow_flags` field surfaces concrete abuse patterns."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"customer_id": {"type": "integer"}},
            "required": ["customer_id"],
        },
    },
    {
        "name": "get_restaurant_history",
        "description": (
            "Restaurant rating, complaint volume, recent low reviews. Use to "
            "gauge whether a 'cold food' / 'missing item' claim is plausible."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"restaurant_id": {"type": "integer"}},
            "required": ["restaurant_id"],
        },
    },
    {
        "name": "get_rider_history",
        "description": (
            "Rider stats: deliveries, verified vs unverified incidents by "
            "type. Use this whenever the complaint is about the rider "
            "(theft, never arrived, rude, late). Many UNverified theft_claims "
            "from a handful of customers means the rider is likely the victim "
            "of spurious claims, not a real problem."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"rider_id": {"type": "integer"}},
            "required": ["rider_id"],
        },
    },
    {
        "name": "find_recent_orders_for_customer",
        "description": (
            "If the customer hasn't given an order id yet but you know their "
            "customer_id (rare — usually you ask), peek at recent orders."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "integer"},
                "limit": {"type": "integer", "default": 5},
            },
            "required": ["customer_id"],
        },
    },
    {
        "name": "search_policy",
        "description": (
            "Search the internal policy + FAQ for guidance on a specific "
            "topic (e.g. 'promo code', 'double charge', 'never arrived'). "
            "Returns the most relevant sections verbatim."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "k": {"type": "integer", "default": 3},
            },
            "required": ["query"],
        },
    },
]


ACTION_TOOLS: list[dict[str, Any]] = [
    {
        "name": "issue_refund",
        "description": (
            "Issue a refund for an order. Method 'wallet_credit' is preferred "
            "when evidence is weaker; 'cash' for clear-cut full refunds when "
            "the customer asks for cash. Multiple refunds on one order sum "
            "and must not exceed the order total."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "order_id": {"type": "integer"},
                "amount_inr": {"type": "integer", "minimum": 1},
                "method": {"type": "string", "enum": ["cash", "wallet_credit"]},
                "reason": {"type": "string"},
            },
            "required": ["order_id", "amount_inr", "method", "reason"],
        },
    },
    {
        "name": "file_complaint",
        "description": (
            "File a formal complaint against the restaurant, rider, or app. "
            "Only file when the complaint is credible per policy — do not "
            "file a rider complaint based purely on an unverified customer "
            "claim that contradicts the rider's clean history."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "order_id": {"type": "integer"},
                "target_type": {"type": "string", "enum": ["restaurant", "rider", "app"]},
                "note": {"type": "string"},
            },
            "required": ["order_id", "target_type"],
        },
    },
    {
        "name": "escalate_to_human",
        "description": (
            "Hand the chat to a human operator. Use for: large-value or "
            "novel situations, weak evidence on a substantial claim, "
            "credible abuse patterns (so a human can review), customer "
            "verbally abusive or threatening chargeback, or when the "
            "customer insists on a human after one triage attempt. Always "
            "include a one-line context summary."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"reason": {"type": "string"}},
            "required": ["reason"],
        },
    },
    {
        "name": "flag_abuse",
        "description": (
            "Flag the customer for support-side abuse review. Use when the "
            "data shows a clear abuse pattern (high complaint rate + many "
            "rejected complaints, repeated theft_claims contradicted by "
            "rider history, frequent recent refunds on high-value orders). "
            "Don't flag on a single suspicious request — needs a pattern."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"reason": {"type": "string"}},
            "required": ["reason"],
        },
    },
    {
        "name": "close",
        "description": (
            "Close the chat. Use when the issue is resolved and the customer "
            "doesn't need anything else, OR when escalating with no further "
            "bot turn needed. Provide a one-line outcome summary."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"outcome_summary": {"type": "string"}},
            "required": ["outcome_summary"],
        },
    },
    {
        "name": "reply",
        "description": (
            "Send your final user-facing message for THIS turn. Always call "
            "this exactly once, last. The text in `message` is what the "
            "customer sees. Keep it warm, plain English, no policy jargon."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"message": {"type": "string"}},
            "required": ["message"],
        },
    },
]


ALL_TOOLS = LOOKUP_TOOLS + ACTION_TOOLS


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def run_lookup(name: str, args: dict[str, Any]) -> Any:
    if name == "get_order":
        return data.get_order(int(args["order_id"]))
    if name == "get_customer_history":
        return data.get_customer_history(int(args["customer_id"]))
    if name == "get_restaurant_history":
        return data.get_restaurant_history(int(args["restaurant_id"]))
    if name == "get_rider_history":
        return data.get_rider_history(int(args["rider_id"]))
    if name == "find_recent_orders_for_customer":
        return data.find_recent_orders_for_customer(
            int(args["customer_id"]), int(args.get("limit", 5))
        )
    if name == "search_policy":
        return policy.search_policy(args["query"], int(args.get("k", 3)))
    raise ValueError(f"unknown lookup tool: {name}")


def is_action(name: str) -> bool:
    return name in {t["name"] for t in ACTION_TOOLS}


def is_lookup(name: str) -> bool:
    return name in {t["name"] for t in LOOKUP_TOOLS}


# ---------------------------------------------------------------------------
# Action validation — last-line defense against bad outputs
# ---------------------------------------------------------------------------


def validate_action(action: dict[str, Any]) -> tuple[bool, str]:
    """Return (ok, reason). Caller should drop bad actions and tell the model."""
    t = action.get("type")
    if t == "issue_refund":
        order_id = action.get("order_id")
        amt = action.get("amount_inr")
        if not isinstance(order_id, int) or not isinstance(amt, int) or amt <= 0:
            return False, "issue_refund needs integer order_id and positive amount_inr"
        if action.get("method") not in {"cash", "wallet_credit"}:
            return False, "method must be 'cash' or 'wallet_credit'"
        order = data.get_order(order_id)
        if "error" in order:
            return False, f"order {order_id} does not exist"
        already = order["already_refunded_inr"]
        total = order["order"]["total_inr"]
        if already + amt > total:
            return (
                False,
                f"refund {amt} + already-refunded {already} exceeds order total {total}",
            )
        return True, "ok"
    if t == "file_complaint":
        if action.get("target_type") not in {"restaurant", "rider", "app"}:
            return False, "target_type must be restaurant|rider|app"
        if not isinstance(action.get("order_id"), int):
            return False, "file_complaint needs integer order_id"
        return True, "ok"
    if t == "escalate_to_human":
        return bool(action.get("reason")), "reason required"
    if t == "flag_abuse":
        return bool(action.get("reason")), "reason required"
    if t == "close":
        return bool(action.get("outcome_summary")), "outcome_summary required"
    return False, f"unknown action type: {t}"


def idempotency_key(action: dict[str, Any]) -> str:
    """Stable key used to dedupe accidental retries of the *same* action.

    Two action calls with identical type + targets + amount within one session
    are treated as duplicates by the agent loop. Internal only — never sent
    to the simulator.
    """
    t = action.get("type", "")
    if t == "issue_refund":
        return f"refund:{action.get('order_id')}:{action.get('amount_inr')}:{action.get('method')}"
    if t == "file_complaint":
        return f"complaint:{action.get('order_id')}:{action.get('target_type')}"
    if t in {"escalate_to_human", "flag_abuse"}:
        return f"{t}:{(action.get('reason') or '').strip()[:80]}"
    if t == "close":
        return f"close:{(action.get('outcome_summary') or '').strip()[:80]}"
    return f"unknown:{json.dumps(action, sort_keys=True, default=str)}"


def to_simulator_action(call_name: str, args: dict[str, Any]) -> dict[str, Any] | None:
    """Translate the agent's action tool call into the wire format the
    simulator expects. Drops fields the simulator doesn't accept."""
    if call_name == "issue_refund":
        return {
            "type": "issue_refund",
            "order_id": args["order_id"],
            "amount_inr": args["amount_inr"],
            "method": args["method"],
        }
    if call_name == "file_complaint":
        return {
            "type": "file_complaint",
            "order_id": args["order_id"],
            "target_type": args["target_type"],
        }
    if call_name == "escalate_to_human":
        return {"type": "escalate_to_human", "reason": args["reason"]}
    if call_name == "flag_abuse":
        return {"type": "flag_abuse", "reason": args["reason"]}
    if call_name == "close":
        return {"type": "close", "outcome_summary": args["outcome_summary"]}
    return None
