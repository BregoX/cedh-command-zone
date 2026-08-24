from fastapi.testclient import TestClient
from app.main import app

def test_health():
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

def test_empty_event_id_is_allowed():
    with TestClient(app) as client:
        assert client.get("/?event_id=&tab=players").status_code == 200
