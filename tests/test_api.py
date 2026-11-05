from fastapi.testclient import TestClient

from agriops.api import app
from agriops.generate import demo

client = TestClient(app)


def test_ingest_endpoint():
    response = client.post("/ingest", json=demo())
    assert response.status_code == 200
    data = response.json()
    assert data["accepted"] == 6
    assert all(check["status"] == "pass" for check in data["quality"])
    assert data["site_activity"]
    assert data["compliance"]
