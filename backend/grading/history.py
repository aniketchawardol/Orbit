"""Buyer order-history signals for fraud scoring.

A return is more suspicious in the context of the buyer's behavior: serial
returners and sudden bursts of returns are classic abuse patterns. We summarize
the buyer's prior orders (excluding the current one) into a soft signal. New
buyers with little history get a dampened signal — thin history is uncertainty,
not guilt.
"""

import logging

log = logging.getLogger(__name__)

_RETURN_STATES = ("RETURN_REQUESTED", "RETURN_RECEIVED", "REFUNDED")


def analyze(buyer_id, exclude_order_id=None) -> dict:
    """Summarize a buyer's return behavior into history signals (never raises)."""
    try:
        from django.utils import timezone
        from marketplace.models import Order

        qs = Order.objects.filter(buyer_id=buyer_id)
        if exclude_order_id:
            qs = qs.exclude(pk=exclude_order_id)

        total = qs.count()
        # An order counts as "returned" if it carries a reason or reached a
        # return/refund state at any point.
        returned = qs.filter(return_reason__gt="").count()
        returned_states = qs.filter(state__in=_RETURN_STATES).count()
        returns_count = max(returned, returned_states)

        since = timezone.now() - timezone.timedelta(days=30)
        recent_returns = (
            qs.filter(return_reason__gt="", updated_at__gte=since).count()
        )

        return_rate = returns_count / total if total else 0.0
        insufficient = total < 3

        flags = []
        if not insufficient and return_rate >= 0.5:
            flags.append("high_return_rate")
        if recent_returns >= 3:
            flags.append("frequent_recent_returns")
        if not insufficient and return_rate >= 0.5 and recent_returns >= 3:
            flags.append("serial_returner")

        if insufficient:
            signal = round(min(return_rate, 0.3), 3)
        else:
            rate_factor = min(1.0, return_rate)
            velocity_factor = min(1.0, recent_returns / 3.0)
            signal = round(min(1.0, 0.6 * rate_factor + 0.4 * velocity_factor), 3)

        return {
            "total_orders": total,
            "returns_count": returns_count,
            "return_rate": round(return_rate, 3),
            "recent_returns_30d": recent_returns,
            "insufficient_history": insufficient,
            "flags": flags,
            "history_fraud_signal": signal,
        }
    except Exception:  # noqa: BLE001 — history is a best-effort signal
        log.warning("history analysis failed", exc_info=True)
        return {
            "total_orders": 0,
            "returns_count": 0,
            "return_rate": 0.0,
            "recent_returns_30d": 0,
            "insufficient_history": True,
            "flags": [],
            "history_fraud_signal": 0.0,
            "error": "history_unavailable",
        }
