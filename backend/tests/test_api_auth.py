from fastapi.testclient import TestClient

from main import app


client = TestClient(app)


def test_health_requires_auth_header():
    response = client.get("/api/health")
    assert response.status_code == 401


def test_health_with_valid_auth_header():
    response = client.get("/api/health", headers={"Authorization": "Bearer dev-secret-token"})
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
