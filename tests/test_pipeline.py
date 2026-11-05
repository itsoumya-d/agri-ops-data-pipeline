from datetime import datetime, timezone

from agriops.enrich import enrich
from agriops.generate import demo
from agriops.ingest import ingest, parse_dt
from agriops.models import Asset, Person, Property
from agriops.quality import run_checks
from agriops.warehouse import Warehouse


def fixtures():
    data = demo()
    props = [Property(**p) for p in data["properties"]]
    people = [Person(p["person_id"], p["name"], p["role"], parse_dt(p["induction_completed_at"]), parse_dt(p["biosecurity_declaration_at"])) for p in data["people"]]
    assets = [Asset(**a) for a in data["assets"]]
    return data, props, people, assets


def test_ingest_dedupes_and_validates():
    data, props, people, assets = fixtures()
    raw = data["events"] + [data["events"][0], {"event_id": "bad", "event_type": "unknown", "person_id": "C1", "property_id": "P1", "occurred_at": "2026-11-03T00:00:00+00:00"}]
    result = ingest(raw, props, people, assets)
    assert len(result.events) == len(data["events"])
    assert result.duplicates == ["E-1"]
    assert any(e["error"].startswith("invalid_event_type") for e in result.errors)


def test_enrichment_flags_missing_induction_and_biosecurity():
    data, props, people, assets = fixtures()
    result = ingest(data["events"], props, people, assets)
    enriched = enrich(result.events, people)
    by_id = {e["event_id"]: e for e in enriched}
    assert "induction_missing" in by_id["E-3"]["flags"]
    assert "biosecurity_missing" in by_id["E-3"]["flags"]
    assert "high_severity_hazard" in by_id["E-2"]["flags"]
    assert "visitor_biosecurity_risk" in by_id["E-5"]["flags"]


def test_warehouse_metrics_and_quality():
    data, props, people, assets = fixtures()
    result = ingest(data["events"], props, people, assets)
    warehouse = Warehouse(":memory:")
    warehouse.load(result.events, people, props, assets)
    activity = warehouse.site_activity()
    assert any(row[2] == 1 for row in activity)
    compliance = warehouse.contractor_compliance()
    assert any(row[0] == "C2" and row[3] == "no" for row in compliance)
    hazards = warehouse.hazard_trends()
    assert hazards and hazards[0][2] == "high"
    checks = run_checks(warehouse.connection)
    assert all(check["status"] == "pass" for check in checks)
