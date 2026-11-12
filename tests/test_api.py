"""Tests de l'API (nécessitent fastapi + httpx ; ignorés sinon)."""
import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture()
def client(demo_env):
    from goutte_deau.api import app
    with TestClient(app) as c:
        yield c


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["model_loaded"] is True


def test_predict_ok(client):
    r = client.get("/v1/predict", params={"date": "2024-12-31"})
    body = r.json()
    assert r.status_code == 200 and 0 <= body["probability"] <= 1
    assert body["risk_label"] and body["mode"] in {"observations", "climatologie"}


def test_predict_validation(client):
    assert client.get("/v1/predict").status_code == 422
    assert client.get("/v1/predict", params={"date": "pas-une-date"}).status_code == 422
    assert client.get("/v1/predict", params={"date": "1950-01-01"}).status_code == 422


def test_history_and_model(client):
    assert len(client.get("/v1/history", params={"days": 10}).json()) == 10
    assert client.get("/v1/history", params={"days": 0}).status_code == 422
    assert client.get("/v1/model").json()["representative"] is False


def test_api_key_enforced(client, monkeypatch):
    monkeypatch.setenv("GD_API_KEY", "s3cret")
    assert client.get("/v1/predict", params={"date": "2024-12-31"}).status_code == 401
    ok = client.get("/v1/predict", params={"date": "2024-12-31"}, headers={"X-API-Key": "s3cret"})
    assert ok.status_code == 200
