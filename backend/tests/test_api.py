from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app)


def test_health() -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "0.1.0"}


def test_optional_hardware_does_not_block_startup() -> None:
    response = client.get("/api/v1/capabilities")
    assert response.status_code == 200
    names = {item["name"] for item in response.json()}
    assert {"video", "hid", "virtual_media", "serial"} <= names
