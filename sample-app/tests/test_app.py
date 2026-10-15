from fastapi.testclient import TestClient
from app import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_release_version(monkeypatch):
    monkeypatch.setenv("APP_VERSION", "demo-123")
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"service": "deployiq-sample", "version": "demo-123"}
