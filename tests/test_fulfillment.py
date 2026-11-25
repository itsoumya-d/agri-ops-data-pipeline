from __future__ import annotations

from datetime import datetime, timezone, timedelta
import pytest

from agriops.fulfillment import BatchOrder, FulfillmentEngine, PickEvent


def test_fulfillment_engine_basic_reconciliation():
    engine = FulfillmentEngine()
    now = datetime(2026, 11, 25, 10, 0, tzinfo=timezone.utc)

    orders = [
        BatchOrder(
            order_id="ORD-001",
            hub_id="HUB-NORTH",
            batch_window="morning",
            sku_id="SKU-PRODUCE-A",
            target_quantity=5,
            scheduled_dispatch_at=now,
        ),
        BatchOrder(
            order_id="ORD-002",
            hub_id="HUB-NORTH",
            batch_window="morning",
            sku_id="SKU-DAIRY-B",
            target_quantity=10,
            scheduled_dispatch_at=now,
        ),
        BatchOrder(
            order_id="ORD-003",
            hub_id="HUB-SOUTH",
            batch_window="morning",
            sku_id="SKU-PRODUCE-A",
            target_quantity=8,
            scheduled_dispatch_at=now,
        ),
    ]

    loaded = engine.load_orders(orders)
    assert loaded == 3

    picks = [
        PickEvent(
            event_id="PCK-101",
            order_id="ORD-001",
            sku_id="SKU-PRODUCE-A",
            picked_quantity=5,
            picker_id="PKR-01",
            picked_at=now + timedelta(minutes=15),
            is_damaged=False,
        ),
        PickEvent(
            event_id="PCK-102",
            order_id="ORD-002",
            sku_id="SKU-DAIRY-B",
            picked_quantity=6,
            picker_id="PKR-02",
            picked_at=now + timedelta(minutes=25),
            is_damaged=False,
        ),
        PickEvent(
            event_id="PCK-103",
            order_id="ORD-002",
            sku_id="SKU-DAIRY-B",
            picked_quantity=2,
            picker_id="PKR-02",
            picked_at=now + timedelta(minutes=26),
            is_damaged=True,
        ),
    ]

    recorded = engine.record_picks(picks)
    assert recorded == 3

    summary = engine.reconcile_hub("HUB-NORTH")
    assert summary.hub_id == "HUB-NORTH"
    assert summary.total_orders == 2
    assert summary.fulfilled_orders == 1  # ORD-001 is fulfilled (5/5)
    assert summary.shortfall_orders == 1  # ORD-002 has only 6 valid units (target 10)
    assert summary.fill_rate_pct == 50.0
    assert summary.total_units_required == 15
    assert summary.total_units_picked == 11
    assert summary.damaged_units == 2

    # Stockout risk detection
    risks = engine.detect_stockout_risks(threshold_fill_rate=90.0)
    assert len(risks) >= 1
    sku_b_risk = next((r for r in risks if r["sku_id"] == "SKU-DAIRY-B"), None)
    assert sku_b_risk is not None
    assert sku_b_risk["demand_units"] == 10
    assert sku_b_risk["supplied_units"] == 6
    assert sku_b_risk["fill_rate_pct"] == 60.0


def test_empty_hub_reconciliation():
    engine = FulfillmentEngine()
    summary = engine.reconcile_hub("NON-EXISTENT")
    assert summary.total_orders == 0
    assert summary.fill_rate_pct == 100.0
    assert summary.total_units_picked == 0
