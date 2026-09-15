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

## Merchant RFID authorization flow

The primary demo flow now starts with a merchant payment request rather than
the legacy CSV simulator:

1. Create a payment from the merchant panel with an INR amount, order ID, and
  customer ID.
2. The payment remains `PENDING` while the reader waits for a card.
3. The ESP32/RFID reader sends one opaque token per line over the configured
  serial port. The backend assigns it to the newest pending payment.
4. The issuer-style checks run, followed by the existing fraud pipeline.
5. An approved payment becomes `AUTHORIZED`, reserves the mock balance, and
  writes the fraud decision to the audit ledger.

For local development, use the **Simulate Card Tap** control with
`RFID_TEST_001`, or call `POST /api/v1/payments/{payment_id}/card-tap` with an
opaque `rfid_token`. The backend never accepts or logs real PAN or CVV data.

Set `RFID_SERIAL_PORT` and optionally `RFID_SERIAL_BAUD` before starting the
server. The serial reader is optional; Flask still starts when no reader is
connected. Payment records and card balances are persisted in
`backend/data/payment_store.json`. Set `PAYMENT_STORE_PATH` to move this file
to another persistent location.

For AWS, this JSON approach is suitable when the backend runs on one EC2
instance with an EBS volume, or on a shared EFS mount. Do not rely on the
local filesystem for durable data on Lambda or an ephemeral container; use S3,
DynamoDB, or a managed database there. The file is written through a temporary
file and atomic replace to reduce corruption risk, but it is still a demo
store and is not designed for multiple backend workers writing concurrently.

### Transaction logs

The backend prints safe log lines for each payment event in the terminal:

```text
transaction=... payment=... event=PAYMENT_CREATED ... status=PENDING
transaction=... payment=... event=CARD_TAP_RECEIVED ... status=PENDING
transaction=... payment=... event=PAYMENT_AUTHORIZED ... status=AUTHORIZED
```

Declined payments include the issuer code and reason, such as
`code=62 reason=CARD_BLOCKED` or `code=51 reason=INSUFFICIENT_FUNDS`. Logs do
not print RFID tokens, UIDs, PANs, or CVVs.

### ESP32 + MFRC522 connection

The repository includes a compatible Arduino sketch at
`hardware/esp32_mfrc522/esp32_mfrc522.ino`. It assumes a standard ESP32
DevKit and an MFRC522 reader using SPI:

| MFRC522 pin | ESP32 DevKit pin |
|---|---|
| 3.3V | 3V3 |
| GND | GND |
| SDA/SS | GPIO 5 |
| SCK | GPIO 18 |
| MOSI | GPIO 23 |
| MISO | GPIO 19 |
| RST | GPIO 27 |

Use **3.3 V only** for the MFRC522 module. Do not power it from 5 V. Connect
the ESP32 to the computer with a USB data cable; no separate UART wires are
needed for this setup. The ESP32 USB serial port is the link read by the
Flask process.

Install the Arduino `MFRC522` library, select the correct ESP32 board and USB
port, then upload the sketch. It prints one line per card tap at `115200`
baud. The sketch maps configured UIDs to `RFID_TEST_001`,
`RFID_LOCKED_001`, and `RFID_LOW_BALANCE_001`. Replace the three
`REPLACE_*_UID` constants with the UIDs from your cards. An unmapped card emits
`UNKNOWN_TOKEN` and is declined. Do not send PAN, CVV, or real payment details.

On Windows, identify the board's COM port in Device Manager or with:

```powershell
python -m serial.tools.list_ports
```

Then install dependencies and start the backend with the port configured:

```powershell
cd quantumLedger\backend
pip install -r requirements.txt
$env:RFID_SERIAL_PORT = "COM5"  # replace COM5 with your actual port
$env:RFID_SERIAL_BAUD = "115200"
python app.py
```

Create a payment in the browser first. The serial worker assigns the next
non-empty token from the reader to the newest pending payment. Check the
connection with `GET /api/v1/reader-status`; it should report `connected: true`.

Do not keep Arduino Serial Monitor open while Flask is running because Windows
normally allows only one process to own the COM port at a time.

The current IoT sketch uses these additional connections:

| Component | ESP32 connection |
|---|---|
| OLED VCC/GND | 3V3/GND |
| OLED SCL/SDA | GPIO 22/GPIO 21 |
| Red LED anode | GPIO 25 through 220-330 ohm resistor |
| Green LED anode | GPIO 26 through 220-330 ohm resistor |
| Blue LED anode | GPIO 32 through 220-330 ohm resistor |
| LED cathodes | GND |
| Buzzer + / - | GPIO 13 / GND |

GPIO 22 is now the MFRC522 reset pin and the OLED SCL pin. Install the
`Adafruit GFX Library` and `Adafruit SSD1306` libraries in Arduino IDE before
compiling the sketch. The blue LED means ready/processing, green means
approved, and red means declined. Flask sends the final result back over the
same USB serial connection.

### Registering physical cards

1. Set `ENROLLMENT_MODE` to `true` in the ESP32 sketch.
2. Upload the sketch while Flask and Serial Monitor are closed.
3. Open Serial Monitor at `115200` baud and tap one card.
4. Copy the value printed after `RFID_UID:`.
5. Set `ENROLLMENT_MODE` back to `false` and replace one of the
  `REPLACE_*_UID` constants with that value.
6. Repeat for the active, locked, and low-balance test cards.
7. Upload the sketch again, close Serial Monitor, and restart Flask.

Normal firmware output must be exactly one opaque token per line. The backend
then resolves each token to its corresponding mock card profile.

This increment stops at authorization. Capture, settlement, refunds,
reversals, and webhooks remain future work. The old simulator endpoints are
retained as a secondary regression/demo path.

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
├── hardware/
│   └── esp32_mfrc522/      # ESP32 + MFRC522 serial adapter sketch
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
| `/api/v1/payments` | POST | Create a merchant payment request and wait for a card |
| `/api/v1/payments/{payment_id}` | GET | Read the current payment status |
| `/api/v1/payments/{payment_id}/card-tap` | POST | Development/test entry point for an opaque RFID token |
| `/api/v1/reader-status` | GET | Report serial reader configuration and connection state |

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
