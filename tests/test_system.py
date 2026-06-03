"""System-level (end-to-end) tests.

Drive the real FastAPI app through its public HTTP + WebSocket surface using
Starlette's in-process TestClient. Entering the client context triggers the
app's startup hook (model warm-up), so a single module-scoped client is reused.
"""

import pytest
from fastapi.testclient import TestClient

from main import app

pytestmark = pytest.mark.system


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:  # runs startup (model warm-up) once
        yield c


# ───────────────────────── HTTP ─────────────────────────
def test_index_serves_dashboard(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "<!DOCTYPE html>" in r.text


def test_metrics_contract(client):
    r = client.get("/metrics")
    assert r.status_code == 200
    body = r.json()
    for key in ("metrics", "classes", "feature_names", "feature_labels"):
        assert key in body
    assert body["classes"] == ["Normal", "DDoS", "PortScan", "BruteForce"]


def test_attack_valid_mode(client):
    r = client.post("/attack", json={"mode": "DDoS"})
    assert r.status_code == 200
    assert r.json() == {"ok": True, "mode": "DDoS"}


def test_attack_invalid_mode_is_rejected(client):
    r = client.post("/attack", json={"mode": "Phishing"})
    assert r.status_code == 400
    assert r.json()["ok"] is False


def test_model_eval_endpoint(client):
    r = client.get("/quality/model-eval")
    assert r.status_code == 200
    body = r.json()
    assert len(body["confusion_matrix"]) == 4
    assert len(body["per_class"]) == 4
    assert 0.0 <= body["accuracy"] <= 1.0


# ───────────────────────── WebSocket ─────────────────────────
def test_traffic_stream_contract(client):
    with client.websocket_connect("/ws/traffic?model=classifier") as ws:
        msg = ws.receive_json()
    for key in ("prediction", "is_threat", "confidence", "feature_contributions"):
        assert key in msg
    assert msg["prediction"] in ("Normal", "DDoS", "PortScan", "BruteForce")


def test_training_stream_emits_epochs_and_done(client):
    with client.websocket_connect("/ws/train") as ws:
        ws.send_json({"epochs": 3, "lr": 0.01})
        events = []
        while True:
            msg = ws.receive_json()
            events.append(msg["event"])
            if msg["event"] == "done":
                break
    assert "start" in events
    assert events.count("epoch") == 3
    assert events[-1] == "done"
