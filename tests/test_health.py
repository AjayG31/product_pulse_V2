from datetime import datetime

from fastapi.testclient import TestClient

from productpulse.main import create_app


def test_health_matches_public_coarse_api_contract():
    app = create_app()
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {"status", "checked_at"}
    assert payload["status"] == "healthy"
    checked_at = datetime.fromisoformat(payload["checked_at"].replace("Z", "+00:00"))
    assert checked_at.utcoffset().total_seconds() == 0
    schema = app.openapi()["components"]["schemas"]["HealthResponse"]
    assert schema["required"] == ["status", "checked_at"]
    assert schema["properties"]["status"]["const"] == "healthy"
    assert schema["additionalProperties"] is False


def test_health_does_not_require_database_or_secret_configuration():
    response = TestClient(create_app()).get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

