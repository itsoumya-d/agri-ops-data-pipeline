from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class Property:
    property_id: str
    name: str
    region: str


@dataclass
class Person:
    person_id: str
    name: str
    role: str
    induction_completed_at: datetime | None = None
    biosecurity_declaration_at: datetime | None = None


@dataclass
class Asset:
    asset_id: str
    property_id: str
    kind: str


@dataclass
class Event:
    event_id: str
    event_type: str
    person_id: str
    property_id: str
    asset_id: str
    occurred_at: datetime
    severity: str = "low"
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class IngestResult:
    events: list[Event]
    duplicates: list[str]
    errors: list[dict[str, str]]


EVENT_TYPES = {"check_in", "check_out", "induction", "hazard", "biosecurity_declaration"}
SEVERITIES = {"low", "medium", "high", "critical"}
