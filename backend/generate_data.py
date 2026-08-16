"""
Step 2: TRANSACTION DATA INPUT
Generates a realistic synthetic transaction dataset (amount, device, location,
IP-risk, merchant category, time, historical behaviour) with a fraud label,
used to train the XGBoost risk-scoring model.
"""
import numpy as np
import pandas as pd

RNG = np.random.default_rng(42)

MERCHANT_CATEGORIES = [
    "grocery", "electronics", "travel", "fuel", "utility",
    "ecommerce", "jewellery", "gaming", "atm_withdrawal", "food_delivery",
]
DEVICE_TYPES = ["mobile_known", "mobile_new", "desktop_known", "desktop_new", "pos_terminal"]
CITIES = ["Chennai", "Bengaluru", "Mumbai", "Delhi", "Coimbatore", "Hyderabad", "Pune", "Kolkata"]


def _sample_row(is_fraud: bool, ambiguous: bool = False) -> dict:
    hour = RNG.integers(0, 24)
    if is_fraud:
        amount = float(RNG.choice([RNG.uniform(8000, 60000), RNG.uniform(200, 800)], p=[0.7, 0.3]))
        device = RNG.choice(["mobile_new", "desktop_new"], p=[0.6, 0.4])
        ip_risk_score = RNG.uniform(0.55, 0.98)
        is_new_merchant = RNG.choice([0, 1], p=[0.25, 0.75])
        distance_from_home_km = RNG.uniform(150, 4000)
        txn_velocity_1h = RNG.integers(3, 15)
        hour = int(RNG.choice(list(range(0, 5)) + list(range(0, 24)), p=None)) if RNG.random() < 0.4 else hour
        avg_historical_amount = float(RNG.uniform(500, 3000))
        account_age_days = int(RNG.integers(1, 400))
    else:
        amount = float(RNG.gamma(2.2, 900))
        device = RNG.choice(["mobile_known", "desktop_known", "pos_terminal"], p=[0.55, 0.25, 0.20])
        ip_risk_score = RNG.uniform(0.0, 0.35)
        is_new_merchant = RNG.choice([0, 1], p=[0.85, 0.15])
        distance_from_home_km = RNG.uniform(0, 60)
        txn_velocity_1h = RNG.integers(0, 3)
        avg_historical_amount = float(RNG.uniform(300, 5000))
        account_age_days = int(RNG.integers(90, 3000))

    if ambiguous:
        # Blend legit-looking and fraud-looking signals so the case genuinely
        # sits in the grey zone between the two classes (mixed evidence).
        amount = float(RNG.uniform(1500, 9000))
        device = RNG.choice(DEVICE_TYPES)
        ip_risk_score = RNG.uniform(0.35, 0.6)
        is_new_merchant = int(RNG.choice([0, 1]))
        distance_from_home_km = RNG.uniform(40, 400)
        txn_velocity_1h = RNG.integers(1, 5)
        avg_historical_amount = float(RNG.uniform(800, 4000))
        account_age_days = int(RNG.integers(30, 1200))
        hour = int(RNG.integers(0, 24))

    merchant_category = RNG.choice(MERCHANT_CATEGORIES)
    city = RNG.choice(CITIES)

    # Measurement noise: real-world sensors/logs are never perfectly clean.
    amount = max(0.0, amount * RNG.normal(1.0, 0.04))
    ip_risk_score = float(np.clip(ip_risk_score + RNG.normal(0, 0.05), 0, 1))
    distance_from_home_km = max(0.0, distance_from_home_km * RNG.normal(1.0, 0.08))

    amount_deviation = round(abs(amount - avg_historical_amount) / max(avg_historical_amount, 1), 3)

    return {
        "amount": round(amount, 2),
        "hour_of_day": int(hour),
        "device_type": device,
        "merchant_category": merchant_category,
        "city": city,
        "ip_risk_score": round(float(ip_risk_score), 3),
        "is_new_merchant": int(is_new_merchant),
        "distance_from_home_km": round(float(distance_from_home_km), 1),
        "txn_velocity_1h": int(txn_velocity_1h),
        "avg_historical_amount": round(avg_historical_amount, 2),
        "amount_deviation": amount_deviation,
        "account_age_days": account_age_days,
        "is_fraud": int(is_fraud),
    }


def generate_dataset(n_rows: int = 6000, fraud_ratio: float = 0.12, ambiguous_ratio: float = 0.08) -> pd.DataFrame:
    n_ambiguous = int(n_rows * ambiguous_ratio)
    n_fraud = int((n_rows - n_ambiguous) * fraud_ratio)
    n_legit = n_rows - n_ambiguous - n_fraud
    # Ambiguous cases are labelled close to a coin flip - they represent the
    # genuinely hard, borderline transactions the XGBoost stage can't resolve.
    rows = (
        [_sample_row(True) for _ in range(n_fraud)]
        + [_sample_row(False) for _ in range(n_legit)]
        + [_sample_row(bool(RNG.random() < 0.5), ambiguous=True) for _ in range(n_ambiguous)]
    )
    df = pd.DataFrame(rows)
    return df.sample(frac=1, random_state=42).reset_index(drop=True)


if __name__ == "__main__":
    df = generate_dataset()
    df.to_csv("transactions.csv", index=False)
    print(df["is_fraud"].value_counts())
    print(df.head())
