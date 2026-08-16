"""
Step 4: XGBOOST MODEL
Trains a gradient-boosted tree classifier that predicts a fraud risk score
in [0, 1] from the engineered transaction features, and classifies each
transaction as LOW / UNCERTAIN / HIGH risk using two thresholds T1 < T2.
"""
import os
import joblib
import numpy as np
import xgboost as xgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score, classification_report

from preprocess import build_training_matrix, to_feature_vector, FEATURE_COLUMNS
from generate_data import generate_dataset

MODEL_PATH = os.path.join(os.path.dirname(__file__), "models", "xgb_fraud_model.joblib")

# Risk-classification thresholds (T1, T2) from the flowchart
T1_LOW_RISK = 0.30
T2_HIGH_RISK = 0.70


def train(save: bool = True):
    df = generate_dataset(n_rows=6000, fraud_ratio=0.12)
    X, y = build_training_matrix(df)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    scale_pos_weight = (y_train == 0).sum() / max((y_train == 1).sum(), 1)
    model = xgb.XGBClassifier(
        n_estimators=250,
        max_depth=4,
        learning_rate=0.08,
        subsample=0.85,
        colsample_bytree=0.85,
        scale_pos_weight=scale_pos_weight,
        eval_metric="auc",
        random_state=42,
    )
    model.fit(X_train, y_train)

    proba = model.predict_proba(X_test)[:, 1]
    auc = roc_auc_score(y_test, proba)
    report = classification_report(y_test, (proba > 0.5).astype(int), digits=3)
    print(f"XGBoost validation AUC: {auc:.4f}")
    print(report)

    if save:
        os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
        joblib.dump(model, MODEL_PATH)
        print(f"Saved model to {MODEL_PATH}")
    return model, auc


_model_cache = None


def load_model():
    global _model_cache
    if _model_cache is None:
        if not os.path.exists(MODEL_PATH):
            _model_cache, _ = train(save=True)
        else:
            _model_cache = joblib.load(MODEL_PATH)
    return _model_cache


def score_transaction(raw_transaction: dict) -> float:
    """Returns the XGBoost fraud risk score in [0, 1] for one transaction."""
    model = load_model()
    X = to_feature_vector(raw_transaction)[FEATURE_COLUMNS]
    return float(model.predict_proba(X)[0, 1])


def classify_risk(score: float) -> str:
    if score <= T1_LOW_RISK:
        return "LOW"
    if score >= T2_HIGH_RISK:
        return "HIGH"
    return "UNCERTAIN"


if __name__ == "__main__":
    train()
