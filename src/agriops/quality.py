from __future__ import annotations

import duckdb

from agriops.models import EVENT_TYPES, SEVERITIES


def run_checks(connection: duckdb.DuckDBPyConnection) -> list[dict[str, object]]:
    checks = []
    def add(name: str, failures: int) -> None:
        checks.append({"check": name, "status": "pass" if failures == 0 else "fail", "failures": failures})
    add("event_id_not_null", connection.execute("SELECT COUNT(*) FROM stg_events WHERE event_id IS NULL").fetchone()[0])
    add("event_id_unique", connection.execute("SELECT COUNT(*) FROM (SELECT event_id FROM stg_events GROUP BY event_id HAVING COUNT(*) > 1)").fetchone()[0])
    placeholders = ",".join("?" for _ in EVENT_TYPES)
    add("event_type_accepted", connection.execute(f"SELECT COUNT(*) FROM stg_events WHERE event_type NOT IN ({placeholders})", list(EVENT_TYPES)).fetchone()[0])
    placeholders = ",".join("?" for _ in SEVERITIES)
    add("severity_accepted", connection.execute(f"SELECT COUNT(*) FROM stg_events WHERE severity NOT IN ({placeholders})", list(SEVERITIES)).fetchone()[0])
    add("person_relationship", connection.execute("SELECT COUNT(*) FROM stg_events e LEFT JOIN people p ON e.person_id = p.person_id WHERE p.person_id IS NULL").fetchone()[0])
    add("property_relationship", connection.execute("SELECT COUNT(*) FROM stg_events e LEFT JOIN properties p ON e.property_id = p.property_id WHERE p.property_id IS NULL").fetchone()[0])
    return checks
