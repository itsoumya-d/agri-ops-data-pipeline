from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class RetailBanner(str, Enum):
    NEW_WORLD = "New World"
    PAKnSAVE = "PAK'nSAVE"
    FOUR_SQUARE = "Four Square"
    DISTRIBUTION_CENTRE = "Landing Drive DC"


class QualityStatus(str, Enum):
    VALID = "valid"
    WARNING = "warning"
    REJECTED = "rejected"


@dataclass
class DataProductContract:
    domain: str
    product_name: str
    version: str
    schema_fields: Dict[str, str]
    freshness_sla_minutes: int
    criticality: str = "tier-1"
    owner_team: str = "Data Engineering Platform"

    def validate_record(self, record: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        for expected_field, expected_type in self.schema_fields.items():
            if expected_field not in record:
                return False, f"Missing required schema field: {expected_field}"
        return True, None


@dataclass
class StoreInventoryEvent:
    event_id: str
    store_id: str
    banner: RetailBanner
    sku: str
    quantity_delta: int
    recorded_at: datetime
    quality_status: QualityStatus = QualityStatus.VALID
    reconciliation_notes: Optional[str] = None


@dataclass
class ColdChainLog:
    consignment_id: str
    origin_dc: str
    destination_store_id: str
    category: str
    target_temp_c: float
    recorded_temp_c: float
    dispatch_at: datetime
    delivery_at: datetime

    @property
    def is_temperature_compliant(self) -> bool:
        # Perishable cold-chain tolerance: +/- 2.5 degrees Celsius from target
        return abs(self.recorded_temp_c - self.target_temp_c) <= 2.5

    @property
    def transit_duration_hours(self) -> float:
        return max(0.0, (self.delivery_at - self.dispatch_at).total_seconds() / 3600.0)


class RetailMeshPipeline:
    """
    Enterprise Retail Data Mesh Engine.
    Governs data-as-a-product contracts, multi-banner store event ingestion,
    cold-chain compliance telemetry, and automated DataOps lineage.
    """

    def __init__(self) -> None:
        self.contracts: Dict[str, DataProductContract] = {}
        self.events: List[StoreInventoryEvent] = []
        self.cold_chain_records: List[ColdChainLog] = []

    def register_contract(self, contract: DataProductContract) -> None:
        key = f"{contract.domain}:{contract.product_name}:{contract.version}"
        self.contracts[key] = contract

    def ingest_inventory_batch(
        self,
        raw_records: List[Dict[str, Any]],
        contract_key: str
    ) -> Dict[str, Any]:
        contract = self.contracts.get(contract_key)
        accepted: List[StoreInventoryEvent] = []
        rejected: List[Dict[str, Any]] = []

        for row in raw_records:
            if contract:
                is_valid, err = contract.validate_record(row)
                if not is_valid:
                    rejected.append({"record": row, "reason": err})
                    continue

            try:
                banner_str = row.get("banner", RetailBanner.NEW_WORLD.value)
                banner = RetailBanner(banner_str)
                event = StoreInventoryEvent(
                    event_id=row["event_id"],
                    store_id=row["store_id"],
                    banner=banner,
                    sku=row["sku"],
                    quantity_delta=int(row["quantity_delta"]),
                    recorded_at=row.get("recorded_at", datetime.now(timezone.utc)),
                    quality_status=QualityStatus.VALID
                )
                # Anomaly detection: single store transaction swing > 10,000 units
                if abs(event.quantity_delta) > 10000:
                    event.quality_status = QualityStatus.WARNING
                    event.reconciliation_notes = "Outlier quantity delta flagged for audit"

                accepted.append(event)
                self.events.append(event)
            except Exception as ex:
                rejected.append({"record": row, "reason": str(ex)})

        return {
            "total_received": len(raw_records),
            "accepted_count": len(accepted),
            "rejected_count": len(rejected),
            "rejected_samples": rejected[:5]
        }

    def record_cold_chain(self, log: ColdChainLog) -> bool:
        self.cold_chain_records.append(log)
        return log.is_temperature_compliant

    def summarize_store_activity(self, store_id: str) -> Dict[str, Any]:
        store_events = [e for e in self.events if e.store_id == store_id]
        total_delta = sum(e.quantity_delta for e in store_events)
        warning_count = sum(1 for e in store_events if e.quality_status == QualityStatus.WARNING)
        banners = list({e.banner.value for e in store_events})

        return {
            "store_id": store_id,
            "banner": banners[0] if banners else None,
            "event_count": len(store_events),
            "net_quantity_delta": total_delta,
            "anomaly_warnings": warning_count
        }

    def build_governance_lineage(self) -> Dict[str, Any]:
        compliant_temp = sum(1 for c in self.cold_chain_records if c.is_temperature_compliant)
        total_shipments = len(self.cold_chain_records)
        compliance_rate = (compliant_temp / total_shipments * 100.0) if total_shipments > 0 else 100.0

        return {
            "registered_contracts": len(self.contracts),
            "total_inventory_events": len(self.events),
            "cold_chain_compliance_rate_pct": round(compliance_rate, 2),
            "healthy_sla": all(c.freshness_sla_minutes <= 60 for c in self.contracts.values()),
            "mesh_status": "operational"
        }
