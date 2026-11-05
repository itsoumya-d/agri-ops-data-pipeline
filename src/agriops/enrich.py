from __future__ import annotations

from datetime import timedelta

from agriops.models import Event, Person

BIOSECURITY_VALID_DAYS = 7
SEVERITY_WEIGHT = {"low": 1, "medium": 2, "high": 4, "critical": 8}


def compliance_flags(event: Event, person: Person) -> list[str]:
    flags: list[str] = []
    if event.event_type != "check_in":
        return flags
    if not person.induction_completed_at or person.induction_completed_at > event.occurred_at:
        flags.append("induction_missing")
    if not person.biosecurity_declaration_at or person.biosecurity_declaration_at < event.occurred_at - timedelta(days=BIOSECURITY_VALID_DAYS):
        flags.append("biosecurity_missing")
    if person.role == "visitor" and "biosecurity_missing" in flags:
        flags.append("visitor_biosecurity_risk")
    return flags


def risk_score(flags: list[str], severity: str = "low") -> int:
    return len(flags) + SEVERITY_WEIGHT.get(severity, 1)


def enrich(events: list[Event], people: list[Person]) -> list[dict]:
    by_person = {p.person_id: p for p in people}
    out = []
    for event in events:
        person = by_person[event.person_id]
        flags = compliance_flags(event, person)
        if event.event_type == "hazard" and event.severity in {"high", "critical"}:
            flags.append("high_severity_hazard")
        out.append({
            "event_id": event.event_id,
            "event_type": event.event_type,
            "person_id": event.person_id,
            "property_id": event.property_id,
            "asset_id": event.asset_id,
            "occurred_at": event.occurred_at.isoformat(),
            "severity": event.severity,
            "flags": flags,
            "risk_score": risk_score(flags, event.severity),
        })
    return out
