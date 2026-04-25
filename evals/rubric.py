"""Pure-Python rubric scoring for the offline eval harness.

Mirrors the simulator's grading axes (refund correctness, refund amount in
range, complaint handling, abuse handling, escalation correctness) using
the same 30/20/15/15/10/10 = 100-point rubric. The 'closed cleanly' criterion
is satisfied automatically by the harness (we always feed all turns).

Inputs:
  scenario['expected']   — the YAML expected block
  actions                — list of simulator-format actions (after to_simulator_action)

Output:
  dict with per-criterion {points_earned, points_max, notes} + total.
"""

from __future__ import annotations

from typing import Any

CRITERIA = [
    ("refund_correctness", 30),
    ("refund_amount", 20),
    ("complaint_handling", 15),
    ("abuse_handling", 15),
    ("escalation_correctness", 10),
    ("closed_cleanly", 10),
]


def _refunds(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [a for a in actions if a.get("type") == "issue_refund"]


def _complaints(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [a for a in actions if a.get("type") == "file_complaint"]


def _has(actions: list[dict[str, Any]], t: str) -> bool:
    return any(a.get("type") == t for a in actions)


def _refund_total(actions: list[dict[str, Any]], order_id: int | None = None) -> int:
    return sum(
        a.get("amount_inr", 0)
        for a in _refunds(actions)
        if order_id is None or a.get("order_id") == order_id
    )


def score(scenario: dict[str, Any], actions: list[dict[str, Any]]) -> dict[str, Any]:
    expected = scenario.get("expected", {})
    refund = expected.get("refund", {}) or {}
    complaint = expected.get("complaint", {}) or {}
    must_escalate = bool(expected.get("escalate", False))
    must_flag = bool(expected.get("flag_abuse", False))
    forbid = expected.get("forbid", []) or []

    result = {c: {"points_earned": 0, "points_max": w, "notes": ""} for c, w in CRITERIA}

    # ------------------------------------------------------------- refund correctness
    must_refund = bool(refund.get("must_issue", False))
    refunds = _refunds(actions)
    refunded = bool(refunds)
    if must_refund and refunded:
        result["refund_correctness"]["points_earned"] = 30
        result["refund_correctness"]["notes"] = "refund issued as expected"
    elif not must_refund and not refunded:
        result["refund_correctness"]["points_earned"] = 30
        result["refund_correctness"]["notes"] = "no refund as expected"
    elif must_refund and not refunded:
        result["refund_correctness"]["notes"] = "expected refund, none issued"
    else:
        result["refund_correctness"]["notes"] = "refund issued when none expected"

    # ------------------------------------------------------------- refund amount
    if must_refund:
        order_id = refund.get("order_id")
        amount = _refund_total(actions, order_id)
        lo = refund.get("min_inr", 0)
        hi = refund.get("max_inr", 10**9)
        allowed_methods = set(refund.get("methods", ["wallet_credit", "cash"]))
        used_methods = {a.get("method") for a in refunds if a.get("order_id") == order_id}
        method_ok = used_methods.issubset(allowed_methods) if used_methods else False
        amount_ok = lo <= amount <= hi
        if amount_ok and method_ok:
            result["refund_amount"]["points_earned"] = 20
            result["refund_amount"]["notes"] = f"₹{amount} via {used_methods}"
        elif amount_ok and not method_ok:
            result["refund_amount"]["points_earned"] = 10
            result["refund_amount"]["notes"] = (
                f"amount ok but wrong method: used {used_methods}, allowed {allowed_methods}"
            )
        elif method_ok and not amount_ok:
            result["refund_amount"]["points_earned"] = 5
            result["refund_amount"]["notes"] = (
                f"method ok but amount {amount} outside [{lo},{hi}]"
            )
        else:
            result["refund_amount"]["notes"] = (
                f"amount {amount} outside [{lo},{hi}]; methods {used_methods}"
            )
    else:
        # No refund expected: full credit if no refund, else 0.
        if not refunded:
            result["refund_amount"]["points_earned"] = 20
            result["refund_amount"]["notes"] = "no refund issued (correct)"
        else:
            result["refund_amount"]["notes"] = (
                f"refund of ₹{_refund_total(actions)} issued when none expected"
            )

    # ------------------------------------------------------------- complaint handling
    must_file = bool(complaint.get("must_file", False))
    target = complaint.get("target_type")
    complaints = _complaints(actions)
    if must_file:
        matched = [c for c in complaints if c.get("target_type") == target]
        if matched:
            result["complaint_handling"]["points_earned"] = 15
            result["complaint_handling"]["notes"] = f"filed against {target}"
        elif complaints:
            wrong = {c.get("target_type") for c in complaints}
            result["complaint_handling"]["points_earned"] = 5
            result["complaint_handling"]["notes"] = (
                f"filed but wrong target {wrong}, expected {target}"
            )
        else:
            result["complaint_handling"]["notes"] = f"no complaint filed (expected {target})"
    else:
        if not complaints:
            result["complaint_handling"]["points_earned"] = 15
            result["complaint_handling"]["notes"] = "no complaint filed (correct)"
        else:
            # Tolerate complaints if not explicitly forbidden against the target
            forbidden_targets: set[str] = set()
            for f in forbid:
                if isinstance(f, dict) and "file_complaint_against" in f:
                    forbidden_targets.update(f["file_complaint_against"])
            bad = [c for c in complaints if c.get("target_type") in forbidden_targets]
            if bad:
                result["complaint_handling"]["notes"] = (
                    f"filed forbidden complaint(s) against {[c.get('target_type') for c in bad]}"
                )
            else:
                result["complaint_handling"]["points_earned"] = 10
                result["complaint_handling"]["notes"] = (
                    "extra complaint filed (allowed but not required)"
                )

    # ------------------------------------------------------------- abuse handling
    flagged = _has(actions, "flag_abuse")
    if must_flag and flagged:
        result["abuse_handling"]["points_earned"] = 15
        result["abuse_handling"]["notes"] = "flagged as expected"
    elif not must_flag and not flagged:
        result["abuse_handling"]["points_earned"] = 15
        result["abuse_handling"]["notes"] = "did not cry wolf"
    elif must_flag and not flagged:
        result["abuse_handling"]["notes"] = "expected abuse flag, none raised"
    else:
        result["abuse_handling"]["notes"] = "flagged abuse without basis"

    # ------------------------------------------------------------- escalation
    escalated = _has(actions, "escalate_to_human")
    if must_escalate and escalated:
        result["escalation_correctness"]["points_earned"] = 10
        result["escalation_correctness"]["notes"] = "escalated as expected"
    elif not must_escalate and not escalated:
        result["escalation_correctness"]["points_earned"] = 10
        result["escalation_correctness"]["notes"] = "no unnecessary escalation"
    elif must_escalate and not escalated:
        result["escalation_correctness"]["notes"] = "expected escalation, none happened"
    else:
        result["escalation_correctness"]["points_earned"] = 5
        result["escalation_correctness"]["notes"] = "escalated when not strictly required"

    # ------------------------------------------------------------- closed cleanly
    # Harness drives all scripted turns; we credit unless the agent crashed mid-flow.
    result["closed_cleanly"]["points_earned"] = 10
    result["closed_cleanly"]["notes"] = "ran all scripted turns"

    # ------------------------------------------------------------- forbid hard-checks
    # Any forbid violation overrides the relevant criterion to 0.
    refund_total_all = _refund_total(actions)
    if "refund_any_amount" in forbid and refund_total_all > 0:
        result["refund_correctness"]["points_earned"] = 0
        result["refund_amount"]["points_earned"] = 0
        result["refund_correctness"]["notes"] += f" | FORBID violated: refunded ₹{refund_total_all}"

    total = sum(c["points_earned"] for c in result.values())
    return {
        "criteria": result,
        "total": total,
        "max": sum(w for _, w in CRITERIA),
    }
