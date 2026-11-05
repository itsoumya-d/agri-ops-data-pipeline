from __future__ import annotations

from datetime import datetime

from agriops.models import EVENT_TYPES, SEVERITIES, Asset, Event, IngestResult, Person, Property


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=__import__("datetime").timezone.utc)
    except ValueError:
        return None


def ingest(raw_events: list[dict], properties: list[Property], people: list[Person], assets: list[Asset]) -> IngestResult:
    property_ids = {p.property_id for p in properties}
    person_ids = {p.person_id for p in people}
    asset_ids = {a.asset_id for a in assets}
    seen: set[str] = set()
    events: list[Event] = []
    duplicates: list[str] = []
    errors: list[dict[str, str]] = []
    for raw in raw_events:
        event_id = str(raw.get("event_id", "")).strip()
        if not event_id:
            errors.append({"event_id": "", "error": "missing_event_id"})
            continue
        if event_id in seen:
            duplicates.append(event_id)
            continue
        seen.add(event_id)
        event_type = str(raw.get("event_type", "")).lower()
        if event_type not in EVENT_TYPES:
            errors.append({"event_id": event_id, "error": f"invalid_event_type:{event_type}"})
            continue
        occurred_at = parse_dt(raw.get("occurred_at"))
        if not occurred_at:
            errors.append({"event_id": event_id, "error": "invalid_occurred_at"})
            continue
        person_id = str(raw.get("person_id", ""))
        property_id = str(raw.get("property_id", ""))
        asset_id = str(raw.get("asset_id", ""))
        if person_id not in person_ids:
            errors.append({"event_id": event_id, "error": f"unknown_person:{person_id}"})
            continue
        if property_id not in property_ids:
            errors.append({"event_id": event_id, "error": f"unknown_property:{property_id}"})
            continue
        if asset_id and asset_id not in asset_ids:
            errors.append({"event_id": event_id, "error": f"unknown_asset:{asset_id}"})
            continue
        severity = str(raw.get("severity", "low")).lower()
        if severity not in SEVERITIES:
            errors.append({"event_id": event_id, "error": f"invalid_severity:{severity}"})
            continue
        events.append(Event(event_id, event_type, person_id, property_id, asset_id, occurred_at, severity, raw.get("payload", {})))
    events.sort(key=lambda e: e.occurred_at)
    return IngestResult(events, duplicates, errors)
