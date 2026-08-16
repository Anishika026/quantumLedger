"""
Flask API for the Quantum-Enhanced Fraud Detection System.
Serves the frontend and exposes the pipeline + audit log over HTTP.
Run:  python app.py   then open http://localhost:5000
"""
import os
import random
import threading
import time
import datetime

import pandas as pd
from flask import Flask, jsonify, request, send_from_directory

from pipeline import run_pipeline
import blockchain
from generate_data import generate_dataset, MERCHANT_CATEGORIES, DEVICE_TYPES, CITIES

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")
SIMULATED_TRANSACTIONS_PATH = os.path.join(os.path.dirname(__file__), "simulated_transactions.csv")
SIMULATOR_INTERVAL_SECONDS = 10

app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path="")

SIMULATOR_RUNNING = False
SIMULATOR_THREAD = None
SIMULATOR_LOCK = threading.Lock()


def _ensure_csv_exists():
    if not os.path.exists(SIMULATED_TRANSACTIONS_PATH):
        pd.DataFrame().to_csv(SIMULATED_TRANSACTIONS_PATH, index=False)


def get_latest_simulated_transaction():
    _ensure_csv_exists()
    try:
        df = pd.read_csv(SIMULATED_TRANSACTIONS_PATH)
    except Exception:
        return None
    if df.empty:
        return None
    return df.iloc[-1].dropna().to_dict()


def get_simulated_transaction_count():
    _ensure_csv_exists()
    try:
        df = pd.read_csv(SIMULATED_TRANSACTIONS_PATH)
        return int(len(df))
    except Exception:
        return 0


def generate_live_mock_transaction():
    mode = random.choice(["legit", "fraud", "uncertain"])
    if mode == "legit":
        fraud_ratio, ambiguous_ratio = 0.0, 0.0
    elif mode == "fraud":
        fraud_ratio, ambiguous_ratio = 1.0, 0.0
    else:
        fraud_ratio, ambiguous_ratio = 0.5, 1.0

    df = generate_dataset(n_rows=1, fraud_ratio=fraud_ratio, ambiguous_ratio=ambiguous_ratio)
    row = df.drop(columns=["is_fraud"]).to_dict(orient="records")[0]
    
    # Get next transaction ID from CSV
    try:
        existing = pd.read_csv(SIMULATED_TRANSACTIONS_PATH)
        if not existing.empty and "transaction_id" in existing.columns:
            last_id = existing["transaction_id"].iloc[-1]
            num = int(last_id.replace("TXN", "")) + 1
            row["transaction_id"] = f"TXN{num:05d}"
        else:
            row["transaction_id"] = "TXN00001"
    except:
        row["transaction_id"] = "TXN00001"
    
    # Add timestamp
    row["timestamp"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    return row


def append_transaction_to_csv(transaction: dict):
    _ensure_csv_exists()
    
    # Ensure transaction has required fields
    if "transaction_id" not in transaction:
        try:
            existing = pd.read_csv(SIMULATED_TRANSACTIONS_PATH)
            if not existing.empty:
                last_id = existing["transaction_id"].iloc[-1]
                num = int(last_id.replace("TXN", "")) + 1
                transaction["transaction_id"] = f"TXN{num:05d}"
            else:
                transaction["transaction_id"] = "TXN00001"
        except:
            transaction["transaction_id"] = "TXN00001"
    
    if "timestamp" not in transaction:
        transaction["timestamp"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    existing = pd.read_csv(SIMULATED_TRANSACTIONS_PATH) if os.path.exists(SIMULATED_TRANSACTIONS_PATH) else pd.DataFrame()
    new_row = pd.DataFrame([transaction])
    combined = pd.concat([existing, new_row], ignore_index=True)
    combined = combined.tail(100)
    combined.to_csv(SIMULATED_TRANSACTIONS_PATH, index=False)


def simulator_worker():
    global SIMULATOR_RUNNING
    while SIMULATOR_RUNNING:
        time.sleep(SIMULATOR_INTERVAL_SECONDS)
        if not SIMULATOR_RUNNING:
            break
        transaction = generate_live_mock_transaction()
        with SIMULATOR_LOCK:
            append_transaction_to_csv(transaction)


@app.route("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/api/simulator-status", methods=["GET"])
def simulator_status():
    return jsonify({
        "ok": True,
        "is_live": bool(SIMULATOR_RUNNING),
        "transaction_count": get_simulated_transaction_count(),
        "message": "Live simulator running." if SIMULATOR_RUNNING else "Simulator offline. Using existing CSV data.",
    })


@app.route("/api/simulator/start", methods=["POST"])
def start_simulator():
    global SIMULATOR_RUNNING, SIMULATOR_THREAD
    if SIMULATOR_RUNNING:
        return jsonify({"ok": True, "is_live": True, "message": "Live simulator already running."})

    with SIMULATOR_LOCK:
        SIMULATOR_RUNNING = True
        SIMULATOR_THREAD = threading.Thread(target=simulator_worker, daemon=True)
        SIMULATOR_THREAD.start()

    return jsonify({
        "ok": True,
        "is_live": True,
        "message": "Live simulation started. The UI will use the newest CSV transaction as it arrives.",
    })


@app.route("/api/simulator/stop", methods=["POST"])
def stop_simulator():
    global SIMULATOR_RUNNING
    SIMULATOR_RUNNING = False
    return jsonify({
        "ok": True,
        "is_live": False,
        "message": "Live simulation stopped. The UI is now in offline test mode.",
    })


@app.route("/api/next-transaction", methods=["GET"])
def next_transaction():
    transaction = get_latest_simulated_transaction()
    if transaction is None:
        return jsonify({"ok": False, "error": "No mock transactions exist yet in the CSV file."}), 404

    if not SIMULATOR_RUNNING:
        return jsonify({
            "ok": True,
            "source": "existing",
            "transaction": transaction,
            "message": "Simulator is not running. Using the latest existing CSV transaction as mock data.",
            "is_live": False,
        })

    return jsonify({
        "ok": True,
        "source": "live",
        "transaction": transaction,
        "message": "Using the newest CSV row from the active simulator.",
        "is_live": True,
    })


@app.route("/api/predict", methods=["POST"])
def predict():
    payload = request.get_json(force=True) or {}
    try:
        result = run_pipeline(payload)
        return jsonify({"ok": True, "result": result})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/sample", methods=["GET"])
def sample():
    """Returns one random realistic transaction for the 'try a sample' button."""
    mode = request.args.get("mode", "random")
    ratio = {"legit": 0.0, "fraud": 1.0, "uncertain": 0.5}.get(mode)
    if mode == "uncertain":
        df = generate_dataset(n_rows=1, fraud_ratio=0.5, ambiguous_ratio=1.0)
    elif ratio is not None:
        df = generate_dataset(n_rows=1, fraud_ratio=ratio, ambiguous_ratio=0.0)
    else:
        df = generate_dataset(n_rows=1, fraud_ratio=random.choice([0.0, 1.0]), ambiguous_ratio=random.choice([0.0, 0.6]))
    row = df.drop(columns=["is_fraud"]).to_dict(orient="records")[0]
    return jsonify({"ok": True, "transaction": row})


@app.route("/api/live-transaction", methods=["GET"])
def live_transaction():
    transaction = get_latest_simulated_transaction()
    if transaction is None:
        return jsonify({"ok": False, "error": "No simulated transactions available yet."}), 404
    return jsonify({"ok": True, "transaction": transaction})


@app.route("/api/audit-log", methods=["GET"])
def audit_log():
    limit = int(request.args.get("limit", 50))
    return jsonify({"ok": True, "blocks": blockchain.get_chain(limit=limit)})


@app.route("/api/audit-log/verify", methods=["GET"])
def audit_verify():
    return jsonify({"ok": True, **blockchain.verify_chain()})


@app.route("/api/meta", methods=["GET"])
def meta():
    return jsonify({
        "ok": True,
        "merchant_categories": MERCHANT_CATEGORIES,
        "device_types": DEVICE_TYPES,
        "cities": CITIES,
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
