"""
Real-Time Fake Transaction Simulator for Fraud Detection Hackathon
Generates realistic synthetic transactions every 10 seconds with ~15-20% suspicious patterns.
No real banking, personal, or payment data is used.

Run: python transaction_simulator.py
Stop: Press Ctrl+C
"""

import time
import random
import signal
import sys
import os
from datetime import datetime
from uuid import uuid4

import numpy as np
import pandas as pd

# Constants - matching generate_data.py for consistency
MERCHANT_CATEGORIES = [
    "grocery", "electronics", "travel", "fuel", "utility",
    "ecommerce", "jewellery", "gaming", "atm_withdrawal", "food_delivery",
]

DEVICE_TYPES = ["mobile_known", "mobile_new", "desktop_known", "desktop_new", "pos_terminal"]

CITIES = ["Chennai", "Bengaluru", "Mumbai", "Delhi", "Coimbatore", "Hyderabad", "Pune", "Kolkata"]

# Simulation config
CSV_FILE = "simulated_transactions.csv"
MAX_ROWS = 100
GENERATION_INTERVAL = 10  # seconds

# Global state
rng = np.random.default_rng(42)
transaction_counter = 0
is_running = True


def signal_handler(sig, frame):
    """Graceful shutdown on Ctrl+C"""
    global is_running
    is_running = False
    print("\n" + "=" * 50)
    print("Shutting down simulator...")
    print("=" * 50)
    sys.exit(0)


def generate_normal_transaction() -> dict:
    """
    Generate a legitimate-looking transaction with realistic patterns.
    ~80% of transactions should be like this.
    """
    txn = {
        "amount": float(rng.gamma(2.2, 900)),
        "hour_of_day": int(rng.integers(0, 24)),
        "device_type": rng.choice(["mobile_known", "desktop_known", "pos_terminal"], p=[0.55, 0.25, 0.20]),
        "ip_risk_score": float(rng.uniform(0.0, 0.35)),
        "is_new_merchant": int(rng.choice([0, 1], p=[0.85, 0.15])),
        "distance_from_home_km": float(rng.uniform(0, 60)),
        "txn_velocity_1h": int(rng.integers(0, 3)),
        "avg_historical_amount": float(rng.uniform(300, 5000)),
        "account_age_days": int(rng.integers(90, 3000)),
        "merchant_category": rng.choice(MERCHANT_CATEGORIES),
        "city": rng.choice(CITIES),
    }
    return txn


def generate_suspicious_transaction() -> dict:
    """
    Generate a suspicious/fraud-like transaction with extreme/unusual patterns.
    ~15-20% of transactions should be like this.
    Intentionally contains suspicious combinations.
    """
    # Choose between high-amount fraud or low-amount fraud
    amount = float(
        rng.choice(
            [rng.uniform(8000, 60000), rng.uniform(200, 800)],
            p=[0.7, 0.3]
        )
    )

    # 40% chance of unusual hour (night time)
    hour = int(rng.choice(list(range(0, 5)) + list(range(23, 24)))) if rng.random() < 0.4 else int(rng.integers(0, 24))

    txn = {
        "amount": amount,
        "hour_of_day": hour,
        "device_type": rng.choice(["mobile_new", "desktop_new"], p=[0.6, 0.4]),
        "ip_risk_score": float(rng.uniform(0.55, 0.98)),
        "is_new_merchant": int(rng.choice([0, 1], p=[0.25, 0.75])),
        "distance_from_home_km": float(rng.uniform(150, 4000)),
        "txn_velocity_1h": int(rng.integers(3, 15)),
        "avg_historical_amount": float(rng.uniform(500, 3000)),
        "account_age_days": int(rng.integers(1, 400)),
        "merchant_category": rng.choice(MERCHANT_CATEGORIES),
        "city": rng.choice(CITIES),
    }
    return txn


def generate_transaction() -> dict:
    """
    Generate a single transaction: 80% normal, 20% suspicious.
    Add metadata (transaction_id, timestamp).
    """
    global transaction_counter
    transaction_counter += 1

    # Generate normal or suspicious based on probability
    if rng.random() < 0.8:
        txn = generate_normal_transaction()
    else:
        txn = generate_suspicious_transaction()

    # Add metadata
    txn["transaction_id"] = f"TXN{transaction_counter:05d}"
    txn["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Round numeric fields for cleaner output
    txn["amount"] = round(txn["amount"], 2)
    txn["ip_risk_score"] = round(txn["ip_risk_score"], 3)
    txn["distance_from_home_km"] = round(txn["distance_from_home_km"], 1)
    txn["avg_historical_amount"] = round(txn["avg_historical_amount"], 2)

    return txn


def format_transaction(txn: dict) -> str:
    """
    Format a transaction dictionary for pretty terminal output.
    """
    output = []
    output.append("\nNEW TRANSACTION")
    output.append("-" * 50)
    output.append(f"Transaction ID          : {txn['transaction_id']}")
    output.append(f"Timestamp               : {txn['timestamp']}")
    output.append(f"Amount                  : ₹{txn['amount']:,.2f}")
    output.append(f"Hour of Day             : {txn['hour_of_day']}")
    output.append(f"Device Type             : {txn['device_type']}")
    output.append(f"IP Risk Score           : {txn['ip_risk_score']:.3f}")
    output.append(f"New Merchant            : {txn['is_new_merchant']}")
    output.append(f"Distance From Home      : {txn['distance_from_home_km']:.1f} km")
    output.append(f"Transactions in 1 Hour  : {txn['txn_velocity_1h']}")
    output.append(f"Average Historical Amt  : ₹{txn['avg_historical_amount']:,.2f}")
    output.append(f"Account Age             : {txn['account_age_days']} days")
    output.append(f"Merchant Category       : {txn['merchant_category']}")
    output.append(f"City                    : {txn['city']}")
    output.append("-" * 50)

    return "\n".join(output)


def save_transaction(txn: dict) -> None:
    """
    Append transaction to CSV file.
    Keep only the latest MAX_ROWS (100) transactions.
    """
    # Prepare data for CSV
    csv_data = {
        "transaction_id": [txn["transaction_id"]],
        "timestamp": [txn["timestamp"]],
        "amount": [txn["amount"]],
        "hour_of_day": [txn["hour_of_day"]],
        "device_type": [txn["device_type"]],
        "ip_risk_score": [txn["ip_risk_score"]],
        "is_new_merchant": [txn["is_new_merchant"]],
        "distance_from_home_km": [txn["distance_from_home_km"]],
        "txn_velocity_1h": [txn["txn_velocity_1h"]],
        "avg_historical_amount": [txn["avg_historical_amount"]],
        "account_age_days": [txn["account_age_days"]],
        "merchant_category": [txn["merchant_category"]],
        "city": [txn["city"]],
    }
    df_new = pd.DataFrame(csv_data)

    # Check if file exists
    if os.path.exists(CSV_FILE):
        # Read existing data
        df_existing = pd.read_csv(CSV_FILE)
        # Combine
        df_combined = pd.concat([df_existing, df_new], ignore_index=True)
        # Keep only last MAX_ROWS
        df_combined = df_combined.tail(MAX_ROWS)
    else:
        df_combined = df_new

    # Write to CSV
    df_combined.to_csv(CSV_FILE, index=False)


def main():
    """
    Main simulator loop.
    Generates and logs transactions every 10 seconds.
    """
    global is_running

    # Setup signal handler for Ctrl+C
    signal.signal(signal.SIGINT, signal_handler)

    # Print startup message
    print("\n" + "=" * 50)
    print("FRAUD DETECTION HACKATHON")
    print("Real-Time Transaction Simulator")
    print("=" * 50)
    print(f"Generating transactions every {GENERATION_INTERVAL} seconds")
    print(f"Normal transactions: ~80%")
    print(f"Suspicious transactions: ~15-20%")
    print(f"CSV file: {CSV_FILE} (keeping latest {MAX_ROWS} rows)")
    print("\nPress Ctrl+C to stop")
    print("=" * 50)

    try:
        while is_running:
            # Generate transaction
            txn = generate_transaction()

            # Print to terminal
            print(format_transaction(txn))

            # Save to CSV
            save_transaction(txn)

            # Wait before next transaction
            time.sleep(GENERATION_INTERVAL)

    except KeyboardInterrupt:
        signal_handler(signal.SIGINT, None)


if __name__ == "__main__":
    main()
