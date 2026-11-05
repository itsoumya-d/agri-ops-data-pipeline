from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI
from pydantic import BaseModel

from agriops.ingest import ingest
from agriops.models import Asset, Person, Property
from agriops.quality import run_checks
from agriops.warehouse import Warehouse

app = FastAPI(title="AgriOps data pipeline", version="0.1.0")
warehouse = Warehouse(":memory:")


class PropertyIn(BaseModel):
    property_id: str
    name: str
    region: str


class PersonIn(BaseModel):
    person_id: str
    name: str
    role: str
    induction_completed_at: str | None = None
    biosecurity_declaration_at: str | None = None


class AssetIn(BaseModel):
    asset_id: str
    property_id: str
    kind: str


class EventIn(BaseModel):
    event_id: str
    event_type: str
    person_id: str
    property_id: str
    asset_id: str = ""
    occurred_at: str
    severity: str = "low"
    payload: dict = {}


class IngestIn(BaseModel):
    properties: list[PropertyIn]
    people: list[PersonIn]
    assets: list[AssetIn] = []
    events: list[EventIn]


def parse(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/ingest")
def run_ingest(payload: IngestIn) -> dict[str, object]:
    properties = [Property(p.property_id, p.name, p.region) for p in payload.properties]
    people = [Person(p.person_id, p.name, p.role, parse(p.induction_completed_at), parse(p.biosecurity_declaration_at)) for p in payload.people]
    assets = [Asset(a.asset_id, a.property_id, a.kind) for a in payload.assets]
    result = ingest([e.model_dump() for e in payload.events], properties, people, assets)
    warehouse.load(result.events, people, properties, assets)
    return {
        "accepted": len(result.events),
        "duplicates": result.duplicates,
        "errors": result.errors,
        "quality": run_checks(warehouse.connection),
        "site_activity": warehouse.site_activity(),
        "compliance": warehouse.contractor_compliance(),
        "hazards": warehouse.hazard_trends(),
    }
