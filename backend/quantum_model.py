"""
Step 5: QUANTUM MODEL (PennyLane)
A Variational Quantum Circuit (VQC) that re-evaluates only the transactions
the XGBoost stage marked UNCERTAIN. Four of the strongest engineered signals
are angle-encoded into 4 qubits, entangled through a ring of CNOTs, and run
through trainable rotation layers; the expectation value of PauliZ on the
first qubit is mapped to a quantum fraud score in [0, 1].
"""
import os
import numpy as np
import pennylane as qml
from pennylane import numpy as pnp

from preprocess import clean, engineer_features

N_QUBITS = 4
N_LAYERS = 3
WEIGHTS_PATH = os.path.join(os.path.dirname(__file__), "models", "vqc_weights.npy")
Q_THRESHOLD = 0.5

dev = qml.device("default.qubit", wires=N_QUBITS)

# The 4 features fed to the quantum circuit, chosen because they carry the
# most signal for the genuinely ambiguous mid-risk band.
QUANTUM_FEATURES = ["amount_deviation", "ip_risk_score", "velocity_risk", "device_risk"]


def _encode_angles(row: dict) -> np.ndarray:
    feats = engineer_features(clean(row))
    raw = np.array([
        min(feats["amount_deviation"], 3.0) / 3.0,
        feats["ip_risk_score"],
        feats["velocity_risk"],
        feats["device_risk"],
    ])
    return raw * np.pi  # scale to a rotation angle in [0, pi]


@qml.qnode(dev)
def _circuit(angles, weights):
    for i in range(N_QUBITS):
        qml.RY(angles[i], wires=i)
    for layer in range(N_LAYERS):
        for i in range(N_QUBITS):
            qml.RY(weights[layer, i, 0], wires=i)
            qml.RZ(weights[layer, i, 1], wires=i)
        for i in range(N_QUBITS):
            qml.CNOT(wires=[i, (i + 1) % N_QUBITS])
    return qml.expval(qml.PauliZ(0))


def _init_weights():
    rng = np.random.default_rng(7)
    return pnp.array(rng.normal(0, 0.4, size=(N_LAYERS, N_QUBITS, 2)), requires_grad=True)


_weights_cache = None


def load_weights():
    """Trains (once) a tiny weight set so the circuit is biased toward the
    same fraud signals the classical model was trained on, then caches it."""
    global _weights_cache
    if _weights_cache is not None:
        return _weights_cache
    if os.path.exists(WEIGHTS_PATH):
        _weights_cache = pnp.array(np.load(WEIGHTS_PATH))
        return _weights_cache

    from generate_data import generate_dataset
    df = generate_dataset(n_rows=300, fraud_ratio=0.5, ambiguous_ratio=1.0)
    rows = df.to_dict(orient="records")
    X = pnp.array([_encode_angles(r) for r in rows])
    y = pnp.array([1.0 if r["is_fraud"] else -1.0 for r in rows])

    weights = _init_weights()
    opt = qml.AdamOptimizer(stepsize=0.15)

    def cost(w):
        preds = pnp.stack([_circuit(x, w) for x in X])
        return pnp.mean((preds - y) ** 2)

    for _ in range(25):
        weights = opt.step(cost, weights)

    os.makedirs(os.path.dirname(WEIGHTS_PATH), exist_ok=True)
    np.save(WEIGHTS_PATH, np.array(weights))
    _weights_cache = weights
    return weights


def quantum_score(raw_transaction: dict) -> dict:
    """Re-scores one uncertain transaction with the VQC.
    Returns the raw expectation value, the mapped [0,1] quantum score,
    and the per-qubit rotation angles used (for UI visualisation)."""
    weights = load_weights()
    angles = _encode_angles(raw_transaction)
    expval = float(_circuit(pnp.array(angles), weights))
    # Map PauliZ expectation [-1, 1] -> fraud probability [0, 1]
    q_score = float(np.clip((1 - expval) / 2, 0, 1))
    return {
        "expectation_value": round(expval, 4),
        "quantum_score": round(q_score, 4),
        "angles_rad": [round(a, 4) for a in angles.tolist()],
        "features_used": QUANTUM_FEATURES,
        "n_qubits": N_QUBITS,
        "n_layers": N_LAYERS,
        "verdict": "FRAUD" if q_score > Q_THRESHOLD else "SAFE",
    }


if __name__ == "__main__":
    load_weights()
    sample = {
        "amount": 4200, "hour_of_day": 2, "device_type": "mobile_new",
        "merchant_category": "electronics", "ip_risk_score": 0.5,
        "is_new_merchant": 1, "distance_from_home_km": 180,
        "txn_velocity_1h": 2, "avg_historical_amount": 1800, "account_age_days": 200,
    }
    print(quantum_score(sample))
