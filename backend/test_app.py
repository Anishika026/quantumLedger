import pandas as pd

from app import app


def test_live_transaction_returns_latest_csv_row(monkeypatch, tmp_path):
    csv_path = tmp_path / "simulated_transactions.csv"
    pd.DataFrame([
        {
            "transaction_id": "TXN00001",
            "timestamp": "2026-01-01 10:00:00",
            "amount": 500.0,
            "hour_of_day": 14,
            "device_type": "mobile_known",
            "merchant_category": "grocery",
            "city": "Chennai",
            "is_new_merchant": 0,
            "ip_risk_score": 0.12,
            "distance_from_home_km": 10.0,
            "txn_velocity_1h": 1,
            "avg_historical_amount": 400.0,
            "account_age_days": 180,
        },
        {
            "transaction_id": "TXN00002",
            "timestamp": "2026-01-01 10:05:00",
            "amount": 1500.0,
            "hour_of_day": 2,
            "device_type": "mobile_new",
            "merchant_category": "electronics",
            "city": "Bengaluru",
            "is_new_merchant": 1,
            "ip_risk_score": 0.9,
            "distance_from_home_km": 250.0,
            "txn_velocity_1h": 5,
            "avg_historical_amount": 500.0,
            "account_age_days": 30,
        },
    ]).to_csv(csv_path, index=False)

    monkeypatch.setattr("app.SIMULATED_TRANSACTIONS_PATH", str(csv_path))

    client = app.test_client()
    response = client.get("/api/live-transaction")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["transaction"]["transaction_id"] == "TXN00002"
    assert payload["transaction"]["amount"] == 1500.0


def test_simulator_status_and_offline_fallback(monkeypatch, tmp_path):
    csv_path = tmp_path / "simulated_transactions.csv"
    pd.DataFrame([
        {
            "transaction_id": "TXN00001",
            "timestamp": "2026-01-01 10:00:00",
            "amount": 500.0,
            "hour_of_day": 14,
            "device_type": "mobile_known",
            "merchant_category": "grocery",
            "city": "Chennai",
            "is_new_merchant": 0,
            "ip_risk_score": 0.12,
            "distance_from_home_km": 10.0,
            "txn_velocity_1h": 1,
            "avg_historical_amount": 400.0,
            "account_age_days": 180,
        }
    ]).to_csv(csv_path, index=False)

    monkeypatch.setattr("app.SIMULATED_TRANSACTIONS_PATH", str(csv_path))
    monkeypatch.setattr("app.SIMULATOR_RUNNING", False)

    client = app.test_client()
    status_response = client.get("/api/simulator-status")
    assert status_response.status_code == 200
    assert status_response.get_json()["is_live"] is False

    next_response = client.get("/api/next-transaction")
    assert next_response.status_code == 200
    payload = next_response.get_json()
    assert payload["source"] == "existing"
    assert payload["transaction"]["transaction_id"] == "TXN00001"
    assert "existing" in payload["message"].lower()


def test_simulator_can_be_started_and_stopped(monkeypatch, tmp_path):
    csv_path = tmp_path / "simulated_transactions.csv"
    pd.DataFrame([]).to_csv(csv_path, index=False)

    monkeypatch.setattr("app.SIMULATED_TRANSACTIONS_PATH", str(csv_path))
    monkeypatch.setattr("app.SIMULATOR_RUNNING", False)
    monkeypatch.setattr("app.SIMULATOR_THREAD", None)

    client = app.test_client()
    start_response = client.post("/api/simulator/start")
    assert start_response.status_code == 200
    assert start_response.get_json()["is_live"] is True

    status_response = client.get("/api/simulator-status")
    assert status_response.status_code == 200
    assert status_response.get_json()["is_live"] is True

    stop_response = client.post("/api/simulator/stop")
    assert stop_response.status_code == 200
    assert stop_response.get_json()["is_live"] is False
