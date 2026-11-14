from datetime import datetime, timedelta, timezone
import pytest

from agriops.retail_mesh import (
    ColdChainLog,
    DataProductContract,
    QualityStatus,
    RetailBanner,
    RetailMeshPipeline,
    StoreInventoryEvent,
)


@pytest.fixture
def mesh_pipeline():
    pipeline = RetailMeshPipeline()
    contract = DataProductContract(
        domain="RetailOperations",
        product_name="StoreDailyInventoryDelta",
        version="v1.0",
        schema_fields={
            "event_id": "str",
            "store_id": "str",
            "banner": "str",
            "sku": "str",
            "quantity_delta": "int"
        },
        freshness_sla_minutes=15,
        criticality="tier-1",
        owner_team="Foodstuffs Data Engineering"
    )
    pipeline.register_contract(contract)
    return pipeline


def test_contract_validation_rejects_missing_fields(mesh_pipeline):
    contract_key = "RetailOperations:StoreDailyInventoryDelta:v1.0"
    raw_records = [
        {
            "event_id": "EVT-1001",
            "store_id": "NW-ALBANY-01",
            "banner": "New World",
            "sku": "PROD-MILK-2L",
            "quantity_delta": 48
        },
        {
            "event_id": "EVT-1002",
            "store_id": "PNS-MT-WELLINGTON",
            # missing 'banner' and 'sku'
            "quantity_delta": 120
        }
    ]

    res = mesh_pipeline.ingest_inventory_batch(raw_records, contract_key)
    assert res["total_received"] == 2
    assert res["accepted_count"] == 1
    assert res["rejected_count"] == 1
    assert "Missing required schema field" in res["rejected_samples"][0]["reason"]


def test_inventory_ingestion_and_outlier_warning(mesh_pipeline):
    contract_key = "RetailOperations:StoreDailyInventoryDelta:v1.0"
    raw_records = [
        {
            "event_id": "EVT-2001",
            "store_id": "FS-COROMANDEL",
            "banner": "Four Square",
            "sku": "BREAD-WHITE-01",
            "quantity_delta": 24
        },
        {
            "event_id": "EVT-2002",
            "store_id": "FS-COROMANDEL",
            "banner": "Four Square",
            "sku": "BULK-FLOUR-50KG",
            "quantity_delta": 50000  # Extreme anomaly
        }
    ]

    res = mesh_pipeline.ingest_inventory_batch(raw_records, contract_key)
    assert res["accepted_count"] == 2
    summary = mesh_pipeline.summarize_store_activity("FS-COROMANDEL")
    assert summary["store_id"] == "FS-COROMANDEL"
    assert summary["event_count"] == 2
    assert summary["net_quantity_delta"] == 50024
    assert summary["anomaly_warnings"] == 1


def test_cold_chain_compliance_and_lineage_metrics(mesh_pipeline):
    now = datetime.now(timezone.utc)
    compliant_log = ColdChainLog(
        consignment_id="CSG-001",
        origin_dc="Landing Drive DC",
        destination_store_id="NW-EASTRIDGE",
        category="Dairy/Chilled",
        target_temp_c=3.0,
        recorded_temp_c=4.1,  # within +2.5 deg tolerance
        dispatch_at=now - timedelta(hours=2),
        delivery_at=now
    )
    breached_log = ColdChainLog(
        consignment_id="CSG-002",
        origin_dc="Landing Drive DC",
        destination_store_id="PNS-BOTANY",
        category="Frozen",
        target_temp_c=-18.0,
        recorded_temp_c=-12.0,  # breached tolerance (+6 deg)
        dispatch_at=now - timedelta(hours=3),
        delivery_at=now
    )

    assert mesh_pipeline.record_cold_chain(compliant_log) is True
    assert mesh_pipeline.record_cold_chain(breached_log) is False
    assert compliant_log.transit_duration_hours == pytest.approx(2.0, abs=0.1)

    lineage = mesh_pipeline.build_governance_lineage()
    assert lineage["registered_contracts"] == 1
    assert lineage["cold_chain_compliance_rate_pct"] == 50.0
    assert lineage["healthy_sla"] is True
    assert lineage["mesh_status"] == "operational"
