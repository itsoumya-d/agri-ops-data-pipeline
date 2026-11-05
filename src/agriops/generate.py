from __future__ import annotations

import json
from pathlib import Path


def demo() -> dict:
    return {
        "properties": [
            {"property_id": "P1", "name": "North Block", "region": "Canterbury"},
            {"property_id": "P2", "name": "South Block", "region": "Canterbury"},
            {"property_id": "P3", "name": "Main Gate", "region": "Canterbury"},
        ],
        "people": [
            {"person_id": "C1", "name": "Sam Contractor", "role": "contractor", "induction_completed_at": "2026-10-01T08:00:00+00:00", "biosecurity_declaration_at": "2026-11-01T07:00:00+00:00"},
            {"person_id": "C2", "name": "Alex Contractor", "role": "contractor", "induction_completed_at": None, "biosecurity_declaration_at": None},
            {"person_id": "V1", "name": "Visitor One", "role": "visitor", "induction_completed_at": "2026-10-20T08:00:00+00:00", "biosecurity_declaration_at": None},
            {"person_id": "E1", "name": "Farm Employee", "role": "employee", "induction_completed_at": "2024-01-01T08:00:00+00:00", "biosecurity_declaration_at": "2026-11-03T07:00:00+00:00"},
        ],
        "assets": [
            {"asset_id": "A1", "property_id": "P1", "kind": "pump"},
            {"asset_id": "A2", "property_id": "P2", "kind": "gate"},
        ],
        "events": [
            {"event_id": "E-1", "event_type": "check_in", "person_id": "C1", "property_id": "P1", "asset_id": "A1", "occurred_at": "2026-11-03T07:30:00+00:00"},
            {"event_id": "E-2", "event_type": "hazard", "person_id": "C1", "property_id": "P1", "asset_id": "A1", "occurred_at": "2026-11-03T09:00:00+00:00", "severity": "high"},
            {"event_id": "E-3", "event_type": "check_in", "person_id": "C2", "property_id": "P2", "asset_id": "", "occurred_at": "2026-11-03T10:00:00+00:00"},
            {"event_id": "E-4", "event_type": "biosecurity_declaration", "person_id": "C1", "property_id": "P1", "asset_id": "", "occurred_at": "2026-11-03T07:00:00+00:00"},
            {"event_id": "E-5", "event_type": "check_in", "person_id": "V1", "property_id": "P3", "asset_id": "", "occurred_at": "2026-11-03T11:00:00+00:00"},
            {"event_id": "E-6", "event_type": "check_out", "person_id": "C1", "property_id": "P1", "asset_id": "A1", "occurred_at": "2026-11-03T15:00:00+00:00"},
        ],
    }


def main() -> None:
    path = Path("data/demo.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(demo(), indent=2))
    print(path)


if __name__ == "__main__":
    main()
