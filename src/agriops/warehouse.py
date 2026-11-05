from __future__ import annotations

from pathlib import Path

import duckdb

from agriops.enrich import enrich
from agriops.models import Asset, Event, Person, Property, SEVERITIES


class Warehouse:
    def __init__(self, path: str | Path = ":memory:") -> None:
        self.connection = duckdb.connect(str(path))
        self._create()

    def _create(self) -> None:
        self.connection.execute("""
        CREATE TABLE IF NOT EXISTS properties (property_id VARCHAR PRIMARY KEY, name VARCHAR, region VARCHAR);
        CREATE TABLE IF NOT EXISTS people (person_id VARCHAR PRIMARY KEY, name VARCHAR, role VARCHAR,
            induction_completed_at TIMESTAMPTZ, biosecurity_declaration_at TIMESTAMPTZ);
        CREATE TABLE IF NOT EXISTS assets (asset_id VARCHAR PRIMARY KEY, property_id VARCHAR, kind VARCHAR);
        CREATE TABLE IF NOT EXISTS stg_events (event_id VARCHAR PRIMARY KEY, event_type VARCHAR,
            person_id VARCHAR, property_id VARCHAR, asset_id VARCHAR, occurred_at TIMESTAMPTZ,
            severity VARCHAR, flags VARCHAR, risk_score INTEGER);
        """)

    def load(self, events: list[Event], people: list[Person], properties: list[Property], assets: list[Asset]) -> None:
        self.connection.execute("DELETE FROM properties"); self.connection.execute("DELETE FROM people")
        self.connection.execute("DELETE FROM assets"); self.connection.execute("DELETE FROM stg_events")
        self.connection.executemany("INSERT INTO properties VALUES (?, ?, ?)", [(p.property_id, p.name, p.region) for p in properties])
        self.connection.executemany("INSERT INTO people VALUES (?, ?, ?, ?, ?)", [
            (p.person_id, p.name, p.role, p.induction_completed_at, p.biosecurity_declaration_at) for p in people
        ])
        self.connection.executemany("INSERT INTO assets VALUES (?, ?, ?)", [(a.asset_id, a.property_id, a.kind) for a in assets])
        rows = []
        for item in enrich(events, people):
            rows.append((item["event_id"], item["event_type"], item["person_id"], item["property_id"],
                         item["asset_id"], item["occurred_at"], item["severity"], ",".join(item["flags"]), item["risk_score"]))
        self.connection.executemany("INSERT INTO stg_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)

    def site_activity(self) -> list[tuple]:
        return self.connection.execute("""
            SELECT property_id, CAST(occurred_at AS DATE) AS activity_date,
                   SUM(CASE WHEN event_type = 'check_in' THEN 1 ELSE 0 END) AS check_ins,
                   COUNT(DISTINCT person_id) AS unique_people,
                   SUM(CASE WHEN event_type = 'hazard' THEN 1 ELSE 0 END) AS hazards,
                   SUM(CASE WHEN event_type = 'biosecurity_declaration' THEN 1 ELSE 0 END) AS biosecurity_declarations
            FROM stg_events
            GROUP BY 1, 2
            ORDER BY 2, 1
        """).fetchall()

    def contractor_compliance(self) -> list[tuple]:
        return self.connection.execute("""
            SELECT p.person_id, p.name, p.role,
                   CASE WHEN p.induction_completed_at IS NOT NULL THEN 'yes' ELSE 'no' END AS induction,
                   CASE WHEN p.biosecurity_declaration_at IS NOT NULL THEN 'yes' ELSE 'no' END AS biosecurity,
                   COUNT(e.event_id) AS events,
                   SUM(CASE WHEN e.event_type = 'hazard' THEN 1 ELSE 0 END) AS hazards
            FROM people p LEFT JOIN stg_events e ON p.person_id = e.person_id
            GROUP BY 1, 2, 3, 4, 5
            ORDER BY p.name
        """).fetchall()

    def hazard_trends(self) -> list[tuple]:
        return self.connection.execute("""
            SELECT property_id, CAST(occurred_at AS DATE) AS day, severity, COUNT(*) AS hazards
            FROM stg_events WHERE event_type = 'hazard'
            GROUP BY 1, 2, 3 ORDER BY 2, 1, 3
        """).fetchall()
