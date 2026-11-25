from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import duckdb


@dataclass
class BatchOrder:
    order_id: str
    hub_id: str
    batch_window: str
    sku_id: str
    target_quantity: int
    scheduled_dispatch_at: datetime


@dataclass
class PickEvent:
    event_id: str
    order_id: str
    sku_id: str
    picked_quantity: int
    picker_id: str
    picked_at: datetime
    is_damaged: bool = False


@dataclass
class ReconciliationSummary:
    hub_id: str
    total_orders: int
    fulfilled_orders: int
    shortfall_orders: int
    fill_rate_pct: float
    total_units_required: int
    total_units_picked: int
    damaged_units: int
    avg_pick_latency_minutes: float


class FulfillmentEngine:
    """Operations data pipeline engine for batch fulfillment and inventory dispatch reconciliation."""

    def __init__(self, db_path: str = ":memory:") -> None:
        self.conn = duckdb.connect(db_path)
        self._init_db()

    def _init_db(self) -> None:
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS batch_orders (
                order_id VARCHAR PRIMARY KEY,
                hub_id VARCHAR,
                batch_window VARCHAR,
                sku_id VARCHAR,
                target_quantity INTEGER,
                scheduled_dispatch_at TIMESTAMPTZ
            );
            CREATE TABLE IF NOT EXISTS pick_events (
                event_id VARCHAR PRIMARY KEY,
                order_id VARCHAR,
                sku_id VARCHAR,
                picked_quantity INTEGER,
                picker_id VARCHAR,
                picked_at TIMESTAMPTZ,
                is_damaged BOOLEAN
            );
        """)

    def load_orders(self, orders: list[BatchOrder]) -> int:
        self.conn.execute("DELETE FROM batch_orders")
        rows = [
            (o.order_id, o.hub_id, o.batch_window, o.sku_id, o.target_quantity, o.scheduled_dispatch_at)
            for o in orders
        ]
        self.conn.executemany("INSERT INTO batch_orders VALUES (?, ?, ?, ?, ?, ?)", rows)
        return len(rows)

    def record_picks(self, picks: list[PickEvent]) -> int:
        rows = [
            (p.event_id, p.order_id, p.sku_id, p.picked_quantity, p.picker_id, p.picked_at, p.is_damaged)
            for p in picks
        ]
        self.conn.executemany("INSERT INTO pick_events VALUES (?, ?, ?, ?, ?, ?, ?)", rows)
        return len(rows)

    def reconcile_hub(self, hub_id: str) -> ReconciliationSummary:
        res = self.conn.execute("""
            WITH order_picks AS (
                SELECT 
                    o.order_id,
                    o.hub_id,
                    o.sku_id,
                    o.target_quantity,
                    o.scheduled_dispatch_at,
                    COALESCE(SUM(CASE WHEN p.is_damaged = FALSE THEN p.picked_quantity ELSE 0 END), 0) AS valid_picked,
                    COALESCE(SUM(CASE WHEN p.is_damaged = TRUE THEN p.picked_quantity ELSE 0 END), 0) AS damaged_picked,
                    MAX(p.picked_at) AS last_picked_at
                FROM batch_orders o
                LEFT JOIN pick_events p ON o.order_id = p.order_id AND o.sku_id = p.sku_id
                WHERE o.hub_id = ?
                GROUP BY o.order_id, o.hub_id, o.sku_id, o.target_quantity, o.scheduled_dispatch_at
            )
            SELECT 
                COUNT(*) AS total_orders,
                SUM(CASE WHEN valid_picked >= target_quantity THEN 1 ELSE 0 END) AS fulfilled_orders,
                SUM(CASE WHEN valid_picked < target_quantity THEN 1 ELSE 0 END) AS shortfall_orders,
                COALESCE(SUM(target_quantity), 0) AS total_units_required,
                COALESCE(SUM(valid_picked), 0) AS total_units_picked,
                COALESCE(SUM(damaged_picked), 0) AS damaged_units,
                COALESCE(AVG(EXTRACT(EPOCH FROM (last_picked_at - scheduled_dispatch_at)) / 60.0), 0.0) AS avg_latency_mins
            FROM order_picks
        """, [hub_id]).fetchone()

        if not res or res[0] == 0:
            return ReconciliationSummary(
                hub_id=hub_id,
                total_orders=0,
                fulfilled_orders=0,
                shortfall_orders=0,
                fill_rate_pct=100.0,
                total_units_required=0,
                total_units_picked=0,
                damaged_units=0,
                avg_pick_latency_minutes=0.0,
            )

        total_orders, fulfilled, shortfall, req_units, picked_units, damaged, latency = res
        fill_rate = (fulfilled / total_orders * 100.0) if total_orders > 0 else 100.0

        return ReconciliationSummary(
            hub_id=hub_id,
            total_orders=int(total_orders),
            fulfilled_orders=int(fulfilled),
            shortfall_orders=int(shortfall),
            fill_rate_pct=round(fill_rate, 2),
            total_units_required=int(req_units),
            total_units_picked=int(picked_units),
            damaged_units=int(damaged),
            avg_pick_latency_minutes=round(float(latency), 2),
        )

    def detect_stockout_risks(self, threshold_fill_rate: float = 95.0) -> list[dict[str, Any]]:
        rows = self.conn.execute("""
            WITH order_picks AS (
                SELECT 
                    o.order_id,
                    o.hub_id,
                    o.sku_id,
                    o.target_quantity,
                    COALESCE(SUM(CASE WHEN p.is_damaged = FALSE THEN p.picked_quantity ELSE 0 END), 0) AS supplied
                FROM batch_orders o
                LEFT JOIN pick_events p ON o.order_id = p.order_id AND o.sku_id = p.sku_id
                GROUP BY o.order_id, o.hub_id, o.sku_id, o.target_quantity
            )
            SELECT 
                hub_id,
                sku_id,
                SUM(target_quantity) AS demand,
                SUM(supplied) AS supplied
            FROM order_picks
            GROUP BY hub_id, sku_id
            HAVING (SUM(supplied) * 100.0 / NULLIF(SUM(target_quantity), 0)) < ? OR SUM(supplied) = 0
            ORDER BY demand DESC
        """, [threshold_fill_rate]).fetchall()

        risks = []
        for hub, sku, demand, supplied in rows:
            rate = round((supplied / demand * 100.0) if demand > 0 else 0.0, 2)
            risks.append({
                "hub_id": hub,
                "sku_id": sku,
                "demand_units": int(demand),
                "supplied_units": int(supplied),
                "fill_rate_pct": rate,
            })
        return risks
