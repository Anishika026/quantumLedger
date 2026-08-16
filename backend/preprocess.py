"""
Step 3: PREPROCESSING
Data cleaning, normalization, and feature engineering shared by both training
and live inference so the model always sees features built the same way.
"""
import numpy as np
import pandas as pd

DEVICE_TYPES = ["mobile_known", "mobile_new", "desktop_known", "desktop_new", "pos_terminal"]
MERCHANT_CATEGORIES = [
    "grocery", "electronics", "travel", "fuel", "utility",
    "ecommerce", "jewellery", "gaming", "atm_withdrawal", "food_delivery",
]

NUMERIC_FEATURES = [
    "amount", "hour_of_day", "ip_risk_score", "is_new_merchant",
    "distance_from_home_km", "txn_velocity_1h", "avg_historical_amount",
    "amount_deviation", "account_age_days", "is_night_txn", "is_high_value",
    "velocity_risk", "device_risk",
]

FEATURE_COLUMNS = NUMERIC_FEATURES + [f"device_{d}" for d in DEVICE_TYPES]

_DEVICE_RISK = {
    "mobile_known": 0.05, "desktop_known": 0.08, "pos_terminal": 0.03,
    "mobile_new": 0.55, "desktop_new": 0.5,
}


def clean(raw: dict) -> dict:
    """Basic cleaning: fill missing values, clip out-of-range numbers, coerce types."""
    row = dict(raw)
    row["amount"] = max(0.0, float(row.get("amount", 0) or 0))
    row["hour_of_day"] = int(row.get("hour_of_day", 12) or 12) % 24
    row["device_type"] = row.get("device_type") or "mobile_known"
    if row["device_type"] not in DEVICE_TYPES:
        row["device_type"] = "mobile_known"
    row["merchant_category"] = row.get("merchant_category") or "ecommerce"
    row["ip_risk_score"] = float(np.clip(row.get("ip_risk_score", 0.1) or 0.1, 0, 1))
    row["is_new_merchant"] = int(bool(row.get("is_new_merchant", 0)))
    row["distance_from_home_km"] = max(0.0, float(row.get("distance_from_home_km", 0) or 0))
    row["txn_velocity_1h"] = max(0, int(row.get("txn_velocity_1h", 0) or 0))
    row["avg_historical_amount"] = max(1.0, float(row.get("avg_historical_amount", 1000) or 1000))
    row["account_age_days"] = max(0, int(row.get("account_age_days", 365) or 365))
    return row


def engineer_features(row: dict) -> dict:
    """Derive engineered signals from the cleaned raw fields."""
    row = dict(row)
    row["amount_deviation"] = round(
        abs(row["amount"] - row["avg_historical_amount"]) / max(row["avg_historical_amount"], 1), 3
    )
    row["is_night_txn"] = int(row["hour_of_day"] < 5 or row["hour_of_day"] >= 23)
    row["is_high_value"] = int(row["amount"] > 3 * row["avg_historical_amount"])
    row["velocity_risk"] = min(1.0, row["txn_velocity_1h"] / 10)
    row["device_risk"] = _DEVICE_RISK.get(row["device_type"], 0.3)
    return row


def to_feature_vector(row: dict) -> pd.DataFrame:
    """Clean -> engineer -> one-hot encode -> return a single-row DataFrame
    with columns matching FEATURE_COLUMNS (model-ready)."""
    cleaned = clean(row)
    feats = engineer_features(cleaned)
    vec = {col: feats.get(col, 0) for col in NUMERIC_FEATURES}
    for d in DEVICE_TYPES:
        vec[f"device_{d}"] = int(feats["device_type"] == d)
    return pd.DataFrame([vec], columns=FEATURE_COLUMNS)


def build_training_matrix(df: pd.DataFrame):
    """Turn the raw generated dataset into X (features) / y (label) for training."""
    rows = df.to_dict(orient="records")
    engineered = [engineer_features(clean(r)) for r in rows]
    feat_df = pd.DataFrame(engineered)
    X = pd.DataFrame({col: feat_df[col] for col in NUMERIC_FEATURES})
    for d in DEVICE_TYPES:
        X[f"device_{d}"] = (feat_df["device_type"] == d).astype(int)
    y = df["is_fraud"].astype(int)
    return X[FEATURE_COLUMNS], y
