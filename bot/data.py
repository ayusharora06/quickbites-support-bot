"""Read-only SQLite lookups exposed to the agent as tools.

Each function returns a JSON-friendly dict that pre-computes the signals the
policy doc cares about (complaint rate, recent refunds, account age,
verified-vs-unverified incident ratio, etc.) so the LLM can reason over
summaries instead of raw rows.

All "recent" / "today" calculations use SNAPSHOT_DATE = 2026-04-13 because
that's when the snapshot was taken.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Any

from .config import DB_PATH, SNAPSHOT_DATE


def _snapshot_dt() -> datetime:
    return datetime.fromisoformat(SNAPSHOT_DATE)


@contextmanager
def _conn():
    con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        yield con
    finally:
        con.close()


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def _days_since(iso: str | None) -> int | None:
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (_snapshot_dt() - dt.replace(tzinfo=None)).days


def get_order(order_id: int) -> dict[str, Any]:
    """Full order detail: order header, items, restaurant, rider,
    any complaints/refunds/reviews/incidents tied to this order."""
    with _conn() as con:
        order = _row_to_dict(
            con.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        )
        if order is None:
            return {"error": f"order {order_id} not found"}

        items = [
            dict(r)
            for r in con.execute(
                "SELECT item_name, qty, price_inr FROM order_items WHERE order_id = ?",
                (order_id,),
            ).fetchall()
        ]
        restaurant = _row_to_dict(
            con.execute(
                "SELECT id, name, cuisine, city, area FROM restaurants WHERE id = ?",
                (order["restaurant_id"],),
            ).fetchone()
        )
        rider = None
        if order["rider_id"] is not None:
            rider = _row_to_dict(
                con.execute(
                    "SELECT id, name, city FROM riders WHERE id = ?",
                    (order["rider_id"],),
                ).fetchone()
            )

        complaints = [
            dict(r)
            for r in con.execute(
                "SELECT id, target_type, target_id, raised_at, description, status, "
                "resolution, resolution_amount_inr "
                "FROM complaints WHERE order_id = ? ORDER BY raised_at",
                (order_id,),
            ).fetchall()
        ]
        refunds = [
            dict(r)
            for r in con.execute(
                "SELECT id, amount_inr, type, issued_at, reason "
                "FROM refunds WHERE order_id = ? ORDER BY issued_at",
                (order_id,),
            ).fetchall()
        ]
        reviews = [
            dict(r)
            for r in con.execute(
                "SELECT id, rating, comment, created_at FROM reviews WHERE order_id = ?",
                (order_id,),
            ).fetchall()
        ]
        incidents = [
            dict(r)
            for r in con.execute(
                "SELECT id, type, reported_at, verified, notes "
                "FROM rider_incidents WHERE order_id = ? ORDER BY reported_at",
                (order_id,),
            ).fetchall()
        ]

    delivered_age_hours = None
    if order.get("delivered_at"):
        try:
            d = datetime.fromisoformat(order["delivered_at"].replace("Z", "+00:00"))
            delivered_age_hours = round(
                (_snapshot_dt() - d.replace(tzinfo=None)).total_seconds() / 3600, 1
            )
        except ValueError:
            pass

    return {
        "order": order,
        "items": items,
        "restaurant": restaurant,
        "rider": rider,
        "delivered_age_hours_from_snapshot": delivered_age_hours,
        "prior_complaints_on_this_order": complaints,
        "prior_refunds_on_this_order": refunds,
        "reviews_on_this_order": reviews,
        "rider_incidents_on_this_order": incidents,
        "already_refunded_inr": sum(r["amount_inr"] for r in refunds),
    }


def get_customer_history(customer_id: int) -> dict[str, Any]:
    """Customer profile + complaint/refund summary + abuse signals."""
    with _conn() as con:
        cust = _row_to_dict(
            con.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)).fetchone()
        )
        if cust is None:
            return {"error": f"customer {customer_id} not found"}

        order_count = con.execute(
            "SELECT COUNT(*) FROM orders WHERE customer_id = ?", (customer_id,)
        ).fetchone()[0]
        delivered_count = con.execute(
            "SELECT COUNT(*) FROM orders WHERE customer_id = ? AND status = 'delivered'",
            (customer_id,),
        ).fetchone()[0]

        complaints = [
            dict(r)
            for r in con.execute(
                "SELECT id, order_id, target_type, raised_at, description, status, "
                "resolution, resolution_amount_inr "
                "FROM complaints WHERE customer_id = ? ORDER BY raised_at DESC",
                (customer_id,),
            ).fetchall()
        ]
        refunds = [
            dict(r)
            for r in con.execute(
                "SELECT id, order_id, amount_inr, type, issued_at, reason "
                "FROM refunds WHERE customer_id = ? ORDER BY issued_at DESC",
                (customer_id,),
            ).fetchall()
        ]

        recent_orders = [
            dict(r)
            for r in con.execute(
                "SELECT id, placed_at, status, total_inr, restaurant_id "
                "FROM orders WHERE customer_id = ? ORDER BY placed_at DESC LIMIT 10",
                (customer_id,),
            ).fetchall()
        ]

    cutoff_30 = (_snapshot_dt() - timedelta(days=30)).isoformat()
    cutoff_90 = (_snapshot_dt() - timedelta(days=90)).isoformat()

    refunds_30d = [r for r in refunds if r["issued_at"] >= cutoff_30]
    refunds_90d = [r for r in refunds if r["issued_at"] >= cutoff_90]
    complaints_90d = [c for c in complaints if c["raised_at"] >= cutoff_90]
    rejected = [c for c in complaints if c["status"] == "rejected"]

    complaint_rate = round(len(complaints) / order_count, 3) if order_count else 0.0
    rejection_rate = round(len(rejected) / len(complaints), 3) if complaints else 0.0

    age_days = _days_since(cust["joined_at"])

    yellow_flags: list[str] = []
    if age_days is not None and age_days < 30 and len(complaints) > 1:
        yellow_flags.append(
            f"NEW_ACCOUNT_MULTI_COMPLAINT: joined {age_days}d ago, {len(complaints)} complaints"
        )
    if len(refunds_30d) >= 3:
        yellow_flags.append(
            f"FREQUENT_REFUNDS_30D: {len(refunds_30d)} refunds in last 30 days, "
            f"total ₹{sum(r['amount_inr'] for r in refunds_30d)}"
        )
    if order_count >= 5 and complaint_rate >= 0.4:
        yellow_flags.append(
            f"HIGH_COMPLAINT_RATE: {len(complaints)}/{order_count} orders ({complaint_rate})"
        )
    if len(complaints) >= 5 and rejection_rate >= 0.4:
        yellow_flags.append(
            f"MANY_REJECTED_COMPLAINTS: {len(rejected)}/{len(complaints)} rejected"
        )

    return {
        "customer": {
            "id": cust["id"],
            "name": cust["name"],
            "city": cust["city"],
            "joined_at": cust["joined_at"],
            "account_age_days": age_days,
            "loyalty_tier": cust["loyalty_tier"],
            "wallet_balance_inr": cust["wallet_balance_inr"],
        },
        "lifetime_orders": order_count,
        "lifetime_delivered": delivered_count,
        "lifetime_complaints": len(complaints),
        "lifetime_refunds_inr": sum(r["amount_inr"] for r in refunds),
        "complaints_last_90d": len(complaints_90d),
        "refunds_last_30d_count": len(refunds_30d),
        "refunds_last_30d_inr": sum(r["amount_inr"] for r in refunds_30d),
        "refunds_last_90d_inr": sum(r["amount_inr"] for r in refunds_90d),
        "complaint_rate": complaint_rate,
        "rejection_rate": rejection_rate,
        "recent_orders": recent_orders,
        "recent_complaints": complaints[:10],
        "recent_refunds": refunds[:10],
        "yellow_flags": yellow_flags,
    }


def get_restaurant_history(restaurant_id: int) -> dict[str, Any]:
    """Restaurant summary: rating, complaint mix, recent reviews."""
    with _conn() as con:
        rest = _row_to_dict(
            con.execute(
                "SELECT * FROM restaurants WHERE id = ?", (restaurant_id,)
            ).fetchone()
        )
        if rest is None:
            return {"error": f"restaurant {restaurant_id} not found"}

        rating_row = con.execute(
            "SELECT ROUND(AVG(rating), 2) AS avg, COUNT(*) AS n "
            "FROM reviews WHERE restaurant_id = ?",
            (restaurant_id,),
        ).fetchone()

        order_count = con.execute(
            "SELECT COUNT(*) FROM orders WHERE restaurant_id = ?", (restaurant_id,)
        ).fetchone()[0]

        complaints = [
            dict(r)
            for r in con.execute(
                "SELECT description, status, resolution, raised_at "
                "FROM complaints WHERE target_type = 'restaurant' AND target_id = ? "
                "ORDER BY raised_at DESC LIMIT 15",
                (restaurant_id,),
            ).fetchall()
        ]
        complaint_count = con.execute(
            "SELECT COUNT(*) FROM complaints WHERE target_type='restaurant' AND target_id=?",
            (restaurant_id,),
        ).fetchone()[0]

        low_reviews = [
            dict(r)
            for r in con.execute(
                "SELECT rating, comment, created_at FROM reviews "
                "WHERE restaurant_id = ? AND rating <= 2 "
                "ORDER BY created_at DESC LIMIT 10",
                (restaurant_id,),
            ).fetchall()
        ]

    return {
        "restaurant": dict(rest),
        "avg_rating": rating_row["avg"],
        "review_count": rating_row["n"],
        "lifetime_orders": order_count,
        "lifetime_restaurant_complaints": complaint_count,
        "complaint_rate_per_order": (
            round(complaint_count / order_count, 3) if order_count else 0.0
        ),
        "recent_complaints": complaints,
        "recent_low_reviews": low_reviews,
    }


def get_rider_history(rider_id: int) -> dict[str, Any]:
    """Rider summary: incident counts split by verified/unverified, by type."""
    with _conn() as con:
        rider = _row_to_dict(
            con.execute("SELECT * FROM riders WHERE id = ?", (rider_id,)).fetchone()
        )
        if rider is None:
            return {"error": f"rider {rider_id} not found"}

        delivered = con.execute(
            "SELECT COUNT(*) FROM orders WHERE rider_id = ? AND status = 'delivered'",
            (rider_id,),
        ).fetchone()[0]

        incidents = [
            dict(r)
            for r in con.execute(
                "SELECT order_id, type, verified, reported_at, notes "
                "FROM rider_incidents WHERE rider_id = ? ORDER BY reported_at DESC",
                (rider_id,),
            ).fetchall()
        ]

        complaint_count = con.execute(
            "SELECT COUNT(*) FROM complaints WHERE target_type='rider' AND target_id=?",
            (rider_id,),
        ).fetchone()[0]

    by_type: dict[str, dict[str, int]] = {}
    for inc in incidents:
        slot = by_type.setdefault(inc["type"], {"verified": 0, "unverified": 0})
        slot["verified" if inc["verified"] else "unverified"] += 1

    verified_total = sum(b["verified"] for b in by_type.values())
    unverified_total = sum(b["unverified"] for b in by_type.values())

    return {
        "rider": {
            "id": rider["id"],
            "name": rider["name"],
            "city": rider["city"],
            "joined_at": rider["joined_at"],
            "tenure_days": _days_since(rider["joined_at"]),
        },
        "lifetime_deliveries": delivered,
        "incidents_by_type": by_type,
        "verified_incidents": verified_total,
        "unverified_incidents": unverified_total,
        "lifetime_rider_complaints": complaint_count,
        "recent_incidents": incidents[:15],
    }


def find_recent_orders_for_customer(customer_id: int, limit: int = 5) -> dict[str, Any]:
    """When the customer doesn't volunteer an order_id, peek at their most
    recent orders to disambiguate. Returns light summaries."""
    with _conn() as con:
        rows = con.execute(
            "SELECT o.id, o.placed_at, o.delivered_at, o.status, o.total_inr, "
            "r.name AS restaurant_name, r.id AS restaurant_id "
            "FROM orders o JOIN restaurants r ON r.id = o.restaurant_id "
            "WHERE o.customer_id = ? ORDER BY o.placed_at DESC LIMIT ?",
            (customer_id, limit),
        ).fetchall()
    return {"orders": [dict(r) for r in rows]}
