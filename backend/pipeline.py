"""
Orchestrates the full flowchart end-to-end:
1. User initiates transaction (input dict)
2. Transaction data input (raw fields)
3. Preprocessing
4. XGBoost model -> risk score + classification
5. Quantum model (only if UNCERTAIN) -> re-score
6. Blockchain audit & logging
Returns a structured trace of every stage for the UI to render.
"""
import time
import uuid

from preprocess import clean, engineer_features
from xgboost_model import score_transaction, classify_risk, T1_LOW_RISK, T2_HIGH_RISK
from quantum_model import quantum_score, Q_THRESHOLD
import blockchain


def run_pipeline(raw_transaction: dict) -> dict:
    t0 = time.time()
    txn_id = raw_transaction.get("transaction_id") or f"TXN-{uuid.uuid4().hex[:10].upper()}"
    raw_transaction = {**raw_transaction, "transaction_id": txn_id}

    stages = []

    # Stage 1-2: user initiates + data input (just echo what was received)
    stages.append({
        "stage": "input",
        "label": "Transaction Data Input",
        "detail": {k: v for k, v in raw_transaction.items() if k != "transaction_id"},
    })

    # Stage 3: preprocessing
    cleaned = clean(raw_transaction)
    engineered = engineer_features(cleaned)
    stages.append({
        "stage": "preprocessing",
        "label": "Preprocessing",
        "detail": {
            "amount_deviation": engineered["amount_deviation"],
            "is_night_txn": bool(engineered["is_night_txn"]),
            "is_high_value": bool(engineered["is_high_value"]),
            "velocity_risk": engineered["velocity_risk"],
            "device_risk": engineered["device_risk"],
        },
    })

    # Stage 4: XGBoost
    xgb_score = score_transaction(raw_transaction)
    risk_band = classify_risk(xgb_score)
    stages.append({
        "stage": "xgboost",
        "label": "XGBoost Model",
        "detail": {
            "risk_score": round(xgb_score, 4),
            "risk_band": risk_band,
            "thresholds": {"T1": T1_LOW_RISK, "T2": T2_HIGH_RISK},
        },
    })

    final_score = xgb_score
    quantum_result = None
    decision = None
    decision_stage = "xgboost"

    if risk_band == "LOW":
        decision = "APPROVE"
    elif risk_band == "HIGH":
        decision = "BLOCK"
    else:
        # Stage 5: Quantum re-scoring for uncertain cases
        quantum_result = quantum_score(raw_transaction)
        final_score = quantum_result["quantum_score"]
        decision = "BLOCK" if quantum_result["verdict"] == "FRAUD" else "APPROVE"
        decision_stage = "quantum"
        stages.append({
            "stage": "quantum",
            "label": "Quantum Model (PennyLane VQC)",
            "detail": quantum_result,
        })

    # Stage 6: Blockchain audit log
    block = blockchain.add_block(raw_transaction, decision, final_score, decision_stage)
    stages.append({
        "stage": "blockchain",
        "label": "Blockchain Audit & Logging",
        "detail": {
            "block_index": block["index"],
            "block_hash": block["hash"],
            "previous_hash": block["previous_hash"],
            "transaction_hash": block["transaction_hash"],
            "timestamp": block["timestamp"],
        },
    })

    return {
        "transaction_id": txn_id,
        "decision": decision,
        "decision_stage": decision_stage,
        "xgboost_score": round(xgb_score, 4),
        "risk_band": risk_band,
        "quantum_result": quantum_result,
        "final_score": round(final_score, 4),
        "stages": stages,
        "block": block,
        "latency_ms": round((time.time() - t0) * 1000, 1),
    }


if __name__ == "__main__":
    result = run_pipeline({
        "amount": 45000, "hour_of_day": 2, "device_type": "mobile_new",
        "merchant_category": "electronics", "ip_risk_score": 0.8,
        "is_new_merchant": 1, "distance_from_home_km": 900,
        "txn_velocity_1h": 5, "avg_historical_amount": 1500, "account_age_days": 60,
    })
    import json
    print(json.dumps(result, indent=2, default=str))
