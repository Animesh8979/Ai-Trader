import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from godmode.dashboard.app import app
from godmode.core.killswitch import get_kill_switch, reset as ks_reset, engage as ks_engage
from godmode.core.db import get_db, reset_db_singleton


@pytest.fixture
def client(tmp_path):
    # Set up test database file override
    db_file = tmp_path / "test_godmode.sqlite3"
    import godmode.core.paths as paths
    orig_db_path = paths.DB_PATH
    paths.DB_PATH = db_file

    import godmode.core.db as db_mod
    import godmode.core.killswitch as ks_mod
    import godmode.core.audit as audit_mod

    db_mod.reset_db_singleton()
    ks_mod._KS = None
    audit_mod._AUDIT = None

    # Override Stop file path for testing
    ks = get_kill_switch()
    orig_stop_file = ks.stop_file
    ks.stop_file = tmp_path / "STOP"

    # Initialize TestClient
    with TestClient(app) as client:
        yield client

    # Cleanup
    ks.stop_file = orig_stop_file
    paths.DB_PATH = orig_db_path
    
    db_mod.reset_db_singleton()
    ks_mod._KS = None
    audit_mod._AUDIT = None


def test_dashboard_home(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "GODMODE TERMINAL" in response.text


def test_dashboard_api_status(client):
    response = client.get("/api/status")
    assert response.status_code == 200
    data = response.json()
    assert "mode" in data
    assert "base_currency" in data
    assert "halted" in data
    assert "positions" in data
    assert "history" in data


def test_dashboard_api_stop_resume(client):
    # Call Stop api
    response = client.post("/api/stop")
    assert response.status_code == 200
    assert response.json()["halted"] is True

    # Call Resume api
    response = client.post("/api/resume")
    assert response.status_code == 200
    assert response.json()["halted"] is False


def test_dashboard_new_api_endpoints(client):
    # Test orders endpoint
    response = client.get("/api/orders")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

    # Test fills endpoint
    response = client.get("/api/fills")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

    # Test decisions endpoint
    response = client.get("/api/decisions")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

    # Test agent messages endpoint
    response = client.get("/api/agent_messages")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

    # Test kill events endpoint
    response = client.get("/api/kill_events")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_dashboard_api_backtest(client, tmp_path):
    # Test backtest validation (missing file)
    req_payload = {
        "strategy": "ema_crossover",
        "data_path": "non_existent_file.csv",
        "start": "2026-06-01"
    }
    response = client.post("/api/backtest/run", json=req_payload)
    assert response.status_code == 200
    assert response.json()["status"] == "error"
    assert "not found" in response.json()["message"]

    # Test backtest success (valid dummy file)
    dummy_csv = tmp_path / "dummy_data.csv"
    dummy_csv.write_text("timestamp,open,high,low,close,volume\n2026-06-01 00:00:00,10,11,9,10,1")
    req_payload["data_path"] = str(dummy_csv)
    response = client.post("/api/backtest/run", json=req_payload)
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

