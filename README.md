# QuantumLedger — Hybrid Classical–Quantum Fraud Detection System

A working implementation of your ORIGINS 2026 pipeline: **XGBoost** for initial
risk scoring, a **PennyLane quantum variational circuit (VQC)** to re-score
transactions the classical model is unsure about, and a **hash-chained
blockchain audit log** for tamper-evident logging — wrapped in a dark,
control-room style web console.

Every box in your flowchart is a real, running piece of code (not mocked):

| # | Flowchart step | File | What it actually does |
|---|---|---|---|
| 1–2 | User initiates / data input | `frontend/index.html`, `backend/app.py` | Form captures amount, device, location, IP risk, merchant, time, history → POSTed to `/api/predict` |
| 3 | Preprocessing | `backend/preprocess.py` | Cleans/clips raw fields, engineers features (amount deviation, night-txn flag, velocity risk, device risk, one-hot device) |
| 4 | XGBoost model | `backend/xgboost_model.py` | Gradient-boosted trees trained on a synthetic 6,000-row transaction dataset, outputs a 0–1 fraud score, classifies LOW / UNCERTAIN / HIGH via thresholds T1=0.30, T2=0.70 |
| 5 | Quantum model (PennyLane) | `backend/quantum_model.py` | A real 4-qubit, 3-layer variational circuit (`default.qubit` simulator) — angle-encodes 4 risk features, trainable RY/RZ rotations + CNOT entanglement, reads out `⟨Z₀⟩` as a quantum fraud score. Only runs for UNCERTAIN cases |
| 6 | Blockchain audit & logging | `backend/blockchain.py` | A local hash-chained ledger: every decision is written as a block with `transaction_hash + decision + timestamp + previous_hash`, with a `/verify` endpoint that recomputes every hash to prove the log hasn't been tampered with |

The frontend (`frontend/`) animates the transaction traveling through each
stage live, shows the actual risk score/thresholds/quantum circuit angles
used, and renders the ledger as it grows.

## Run it

```bash
cd backend
pip install -r requirements.txt
python app.py
```

Then open **http://localhost:5000**. The first request will take a few
seconds — it trains the XGBoost model and the quantum circuit's weights
once and caches them under `backend/models/`.

## Project structure

```
fraud-detection-system/
├── backend/
│   ├── app.py              # Flask API + static file server
│   ├── pipeline.py         # Orchestrates steps 1-6 end to end
│   ├── generate_data.py    # Synthetic transaction dataset generator
│   ├── preprocess.py       # Cleaning + feature engineering (step 3)
│   ├── xgboost_model.py    # XGBoost training + scoring (step 4)
│   ├── quantum_model.py    # PennyLane VQC re-scoring (step 5)
│   ├── blockchain.py       # Hash-chained audit ledger (step 6)
│   ├── requirements.txt
│   ├── models/             # generated: trained XGBoost model + VQC weights
│   └── data/                # generated: audit_chain.json ledger
├── frontend/
│   ├── index.html
│   ├── style.css
│   └── app.js
└── README.md
```

## How the pipeline decides

```
score = XGBoost(transaction)
if score <= 0.30:        decision = APPROVE   (LOW risk)
elif score >= 0.70:      decision = BLOCK      (HIGH risk)
else:                     # UNCERTAIN
    q = QuantumVQC(transaction)
    decision = BLOCK if q.quantum_score > 0.5 else APPROVE

log_to_blockchain(transaction_hash, decision, timestamp)
```

## API reference

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/predict` | POST | Runs a transaction through the full pipeline, returns every stage's detail |
| `/api/sample?mode=legit\|fraud\|uncertain\|random` | GET | Returns a synthetic transaction matching that scenario, for demoing |
| `/api/audit-log?limit=N` | GET | Returns the last N ledger blocks, newest first |
| `/api/audit-log/verify` | GET | Recomputes the whole hash chain and reports whether it's intact |
| `/api/meta` | GET | Device/merchant/city options for the form dropdowns |

## Notes for your pitch

- **Why XGBoost first, quantum second**: XGBoost handles the ~90% of
  transactions that are clearly legit or clearly fraudulent cheaply; the
  quantum circuit is only invoked for the genuinely ambiguous band, which is
  where a different inductive bias (superposition/entanglement capturing
  feature *correlations* classical trees can miss) has the most to add — and
  it keeps the system practical, since simulating/running quantum circuits
  for every transaction wouldn't scale.
- **Why a hash chain, not a public blockchain**: for an audit log you need
  tamper-evidence and a verifiable history, not decentralization or
  consensus — the same cryptographic primitive (hash-linked blocks) that
  underlies real blockchains, without the overhead of a network. You can
  swap `blockchain.py`'s storage for an actual chain (e.g. writing block
  hashes to Polygon/Hyperledger) later without changing the rest of the
  pipeline.
- **Swapping in real data**: replace `generate_data.py`'s output with a real
  labelled transaction dataset (e.g. a Kaggle credit-card-fraud CSV) and
  retrain — `preprocess.py` and `xgboost_model.py` don't need to change as
  long as the column names line up.
