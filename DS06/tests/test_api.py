from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"

def test_delay_rejects_missing_features():
    r = client.post("/predict_project_delay", json={"features": {}})
    assert r.status_code == 422

def test_win_rejects_missing_features():
    r = client.post("/predict_opportunity_success", json={"features": {}})
    assert r.status_code == 422
