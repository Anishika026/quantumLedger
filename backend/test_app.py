import pandas as pd

from app import app
from payment_flow import PaymentStore


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


def _payment_request(amount=250000):
    return {
        "amount": amount,
        "currency": "INR",
        "merchant": {"merchant_id": "merchant_001"},
        "customer": {"customer_id": "customer_test_001"},
        "order": {
            "order_id": "order_payment_test",
            "amount": amount,
            "description": "Test payment",
        },
        "payment_method": {"type": "CARD"},
    }


def test_payment_request_waits_for_card_and_authorizes(monkeypatch):
    monkeypatch.setattr("app.PAYMENT_STORE", PaymentStore())
    monkeypatch.setattr("payment_flow.pipeline.run_pipeline", lambda payload: {
        "decision": "APPROVE",
        "decision_stage": "xgboost",
        "final_score": 0.1,
        "stages": [],
        "transaction_id": payload["transaction_id"],
    })
    client = app.test_client()

    create_response = client.post("/api/v1/payments", json=_payment_request())
    assert create_response.status_code == 201
    payment = create_response.get_json()["payment"]
    assert payment["status"] == "PENDING"
    assert payment["reader_status"] == "WAITING_FOR_CARD"

    tap_response = client.post(
        f"/api/v1/payments/{payment['payment_id']}/card-tap",
        json={"rfid_token": "RFID_TEST_001"},
    )
    assert tap_response.status_code == 200
    authorized = tap_response.get_json()["payment"]
    assert authorized["status"] == "AUTHORIZED"
    assert authorized["authorization"]["response_code"] == "00"
    assert authorized["card"]["masked_pan"] == "**** **** **** 1001"
    assert "card_token" not in authorized["card"]


def test_unknown_card_is_declined_without_sensitive_data(monkeypatch):
    monkeypatch.setattr("app.PAYMENT_STORE", PaymentStore())
    client = app.test_client()

    create_response = client.post("/api/v1/payments", json=_payment_request(1000))
    payment_id = create_response.get_json()["payment"]["payment_id"]
    tap_response = client.post(
        f"/api/v1/payments/{payment_id}/card-tap",
        json={"rfid_token": "UNKNOWN_TOKEN"},
    )

    assert tap_response.status_code == 200
    declined = tap_response.get_json()["payment"]
    assert declined["status"] == "DECLINED"
    assert declined["authorization"]["reason"] == "INVALID_CARD"
    assert declined["card"] is None


def test_payment_request_rejects_order_amount_mismatch():
    client = app.test_client()
    payload = _payment_request()
    payload["order"]["amount"] = 1

    response = client.post("/api/v1/payments", json=payload)

    assert response.status_code == 400
    assert "match" in response.get_json()["error"]


def test_locked_card_is_declined(monkeypatch):
    monkeypatch.setattr("app.PAYMENT_STORE", PaymentStore())
    client = app.test_client()
    payment = client.post("/api/v1/payments", json=_payment_request(1000)).get_json()["payment"]

    response = client.post(
        f"/api/v1/payments/{payment['payment_id']}/card-tap",
        json={"rfid_token": "RFID_LOCKED_001"},
    )

    result = response.get_json()["payment"]
    assert result["status"] == "DECLINED"
    assert result["authorization"]["reason"] == "CARD_BLOCKED"


def test_low_balance_card_is_declined(monkeypatch):
    monkeypatch.setattr("app.PAYMENT_STORE", PaymentStore())
    client = app.test_client()
    payment = client.post("/api/v1/payments", json=_payment_request(101)).get_json()["payment"]

    response = client.post(
        f"/api/v1/payments/{payment['payment_id']}/card-tap",
        json={"rfid_token": "RFID_LOW_BALANCE_001"},
    )

    result = response.get_json()["payment"]
    assert result["status"] == "DECLINED"
    assert result["authorization"]["reason"] == "INSUFFICIENT_FUNDS"
