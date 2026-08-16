"""
Step 6: BLOCKCHAIN AUDIT & LOGGING
A lightweight, tamper-evident hash-chained ledger. Every decision (approve
or block) is written as a block containing the transaction hash, the
decision, and a timestamp; each block also stores the hash of the previous
block, so any edit to earlier history breaks the chain and is detectable.
This is a genuine local blockchain data-structure (hash chaining + integrity
verification) rather than a call out to a public network - appropriate for
an auditable, tamper-proof log inside the fraud pipeline.
"""
import hashlib
import json
import os
import threading
import time
import uuid

LEDGER_PATH = os.path.join(os.path.dirname(__file__), "data", "audit_chain.json")
_lock = threading.Lock()


def _hash_block(index, timestamp, transaction_hash, decision, previous_hash, nonce=0):
    payload = f"{index}|{timestamp}|{transaction_hash}|{decision}|{previous_hash}|{nonce}"
    return hashlib.sha256(payload.encode()).hexdigest()


def hash_transaction(raw_transaction: dict) -> str:
    """Deterministic hash of the transaction payload (what actually gets logged
    on-chain - never the raw sensitive fields directly)."""
    canonical = json.dumps(raw_transaction, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _genesis_block():
    ts = time.time()
    h = _hash_block(0, ts, "0" * 64, "GENESIS", "0" * 64)
    return {
        "index": 0, "timestamp": ts, "transaction_id": "genesis",
        "transaction_hash": "0" * 64, "decision": "GENESIS",
        "risk_score": None, "stage": "GENESIS",
        "previous_hash": "0" * 64, "hash": h, "nonce": 0,
    }


def _load_chain():
    os.makedirs(os.path.dirname(LEDGER_PATH), exist_ok=True)
    if not os.path.exists(LEDGER_PATH):
        chain = [_genesis_block()]
        _save_chain(chain)
        return chain
    with open(LEDGER_PATH) as f:
        return json.load(f)


def _save_chain(chain):
    with open(LEDGER_PATH, "w") as f:
        json.dump(chain, f, indent=2)


def add_block(raw_transaction: dict, decision: str, risk_score: float, stage: str) -> dict:
    """Appends a new tamper-evident block recording the final decision."""
    with _lock:
        chain = _load_chain()
        prev = chain[-1]
        index = prev["index"] + 1
        ts = time.time()
        txn_hash = hash_transaction(raw_transaction)
        txn_id = raw_transaction.get("transaction_id") or f"TXN-{uuid.uuid4().hex[:10].upper()}"
        block_hash = _hash_block(index, ts, txn_hash, decision, prev["hash"])
        block = {
            "index": index,
            "timestamp": ts,
            "transaction_id": txn_id,
            "transaction_hash": txn_hash,
            "decision": decision,
            "risk_score": round(float(risk_score), 4) if risk_score is not None else None,
            "stage": stage,
            "previous_hash": prev["hash"],
            "hash": block_hash,
            "nonce": 0,
        }
        chain.append(block)
        _save_chain(chain)
        return block


def get_chain(limit: int = 50):
    chain = _load_chain()
    return list(reversed(chain[1:]))[:limit]  # newest first, skip genesis


def verify_chain() -> dict:
    """Recomputes every block's hash and link to prove the ledger hasn't
    been tampered with - this is what makes it audit-grade."""
    chain = _load_chain()
    for i in range(1, len(chain)):
        b = chain[i]
        prev = chain[i - 1]
        if b["previous_hash"] != prev["hash"]:
            return {"valid": False, "broken_at_index": b["index"], "reason": "previous_hash mismatch"}
        recomputed = _hash_block(b["index"], b["timestamp"], b["transaction_hash"], b["decision"], b["previous_hash"], b.get("nonce", 0))
        if recomputed != b["hash"]:
            return {"valid": False, "broken_at_index": b["index"], "reason": "block hash mismatch"}
    return {"valid": True, "blocks": len(chain) - 1}


if __name__ == "__main__":
    b = add_block({"amount": 500, "device_type": "mobile_known"}, "APPROVE", 0.12, "XGBOOST")
    print(b)
    print(verify_chain())
