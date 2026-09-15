# Implementation Status

Updated: 2026-09-14

## Current Slice

The repository is transitioning from a CSV-driven fraud simulation to a merchant payment authorization flow.

## Working Before This Change

- Flask serves the frontend and fraud API.
- The legacy simulator generates synthetic transactions and stores the latest 100 rows in CSV.
- `/api/predict` runs preprocessing, XGBoost scoring, optional PennyLane quantum scoring, and hash-chain audit logging.
- `/api/audit-log/verify` validates the local audit chain.
- `schema.json` defines the intended merchant, gateway, authorization, issuer, and payment state models.

## Implemented In This Slice

- In-memory payment, order, transaction, authorization, mock-card, and issuer-account records.
- Merchant payment-request creation with validation.
- Opaque RFID token lookup with seeded test cards.
- Serial reader adapter boundary plus an injectable fake reader for tests.
- Authorization-only processing that reuses the fraud pipeline.
- Issuer-style checks for card status, expiry, account status, available balance, and fraud decision.
- Safe payment responses that do not expose raw card identifiers.
- ESP32 + MFRC522 Arduino adapter sketch using the repository's serial token protocol.
- UID-to-token mapping for active, locked, low-balance, and unknown cards.
- Optional enrollment mode that prints `RFID_UID:<UID>` without emitting a payment token.
- Regression tests for locked-card and low-balance-card declines.
- Safe console logs for payment creation, card tap, approval, and decline events.
- JSON persistence for cards, balances, payments, transactions, and authorizations.
- ESP32 buzzer, red/green/blue LED, and OLED status feedback with Flask result responses.

## Not Yet Implemented

- Merchant web form and payment status UI.
- Physical ESP32 firmware upload/verification through Arduino IDE.
- Multi-worker/cloud-safe persistence and production database semantics.
- Capture, settlement, refund, reversal, and webhook flows.
- Real card networks, banks, credentials, PAN, or CVV.

## Hardware Contract

The ESP32/RFID reader should send one opaque card token per line over a configurable serial port. Example test event:

```text
RFID_TEST_001
```

The token is a lookup key only. It is not a PAN and must not contain or represent real card credentials.

## Validation Status

- Backend implementation: working; direct payment-service smoke test passed.
- Focused payment tests: added, but pytest is blocked by the local Python installation importing `C:\Users\anish\AppData\Local\Programs\Python\Python314\py.py` instead of pytest's expected `py.path` package.
- Existing simulator regression tests: not run for the same pytest environment blocker.
- Browser flow: JavaScript syntax and editor diagnostics pass; browser interaction still needs a manual run.
- Serial environment: ESP32 detected on `COM13`; Flask reader reports connected at `115200`.
- Physical ESP32 test: mapping constants require real card UIDs; upload and multi-card tap test remain pending.
- Hardware signal test: sketch updated for supplied pins; upload requires Adafruit GFX and SSD1306 libraries.
- JSON restart persistence smoke test: passed with a temporary store path.

## Latest Verification

- `python -m py_compile app.py payment_flow.py rfid_reader.py test_app.py`: passed.
- `node --check ../frontend/app.js`: passed.
- Direct payment-service smoke test: `PENDING` -> `AUTHORIZED`, response code `00`, masked card returned, no raw card token returned.
- Editor diagnostics: no errors in touched files.
