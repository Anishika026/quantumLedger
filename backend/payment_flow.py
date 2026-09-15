"""JSON-backed merchant payment authorization flow for the demo environment."""

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from threading import RLock
from uuid import uuid4

import pipeline

LOGGER = logging.getLogger("quantumledger.payments")

SUPPORTED_CURRENCY = "INR"
DEFAULT_RISK_CONTEXT = {
    "device_type": "pos_terminal",
    "merchant_category": "ecommerce",
    "city": "Bengaluru",
    "ip_risk_score": 0.05,
    "is_new_merchant": 0,
    "distance_from_home_km": 10,
    "txn_velocity_1h": 1,
    "avg_historical_amount": 2500,
    "account_age_days": 900,
}
STORE_PATH = os.getenv(
    "PAYMENT_STORE_PATH",
    os.path.join(os.path.dirname(__file__), "data", "payment_store.json"),
)
PAYMENT_STATUSES = {
    "CREATED", "PENDING", "REQUIRES_AUTHENTICATION", "AUTHORIZED",
    "DECLINED", "FAILED",
}


class PaymentValidationError(ValueError):
    """Raised when a merchant request does not satisfy the payment contract."""


class PaymentStore:
    """Owns JSON-backed payment records and seeded, non-sensitive card profiles."""

    def __init__(self):
        self._lock = RLock()
        self.payments = {}
        self.orders = {}
        self.transactions = {}
        self.authorizations = {}
        self.cards = {
            "RFID_TEST_001": {
                "card_token": "card_tok_test_001",
                "masked_pan": "**** **** **** 1001",
                "network": "VISA",
                "expiry_month": 12,
                "expiry_year": 2030,
                "status": "ACTIVE",
                "user_id": "user_test_001",
                "account_id": "acct_test_001",
                "account_status": "ACTIVE",
                "available_balance": 1000000000,
                "customer_id": "customer_test_001",
            },
            "RFID_LOCKED_001": {
                "card_token": "card_tok_locked_001",
                "masked_pan": "**** **** **** 2001",
                "network": "MASTERCARD",
                "expiry_month": 12,
                "expiry_year": 2030,
                "status": "LOCKED",
                "user_id": "user_test_002",
                "account_id": "acct_test_002",
                "account_status": "ACTIVE",
                "available_balance": 500000,
                "customer_id": "customer_test_002",
            },
            "RFID_QUANTUM_001": {
                "card_token": "card_tok_quantum_001",
                "masked_pan": "**** **** **** 4001",
                "network": "RUPAY",
                "expiry_month": 12,
                "expiry_year": 2030,
                "status": "ACTIVE",
                "user_id": "user_test_004",
                "account_id": "acct_test_004",
                "account_status": "ACTIVE",
                "available_balance": 1000000000,
                "customer_id": "customer_test_004",
            },
            "RFID_LOW_BALANCE_001": {
                "card_token": "card_tok_low_balance_001",
                "masked_pan": "**** **** **** 3001",
                "network": "RUPAY",
                "expiry_month": 12,
                "expiry_year": 2030,
                "status": "ACTIVE",
                "user_id": "user_test_003",
                "account_id": "acct_test_003",
                "account_status": "ACTIVE",
                "available_balance": 100,
                "customer_id": "customer_test_003",
            },
        }
        self.merchants = {
            "merchant_001": {
                "merchant_id": "merchant_001",
                "name": "Quantum Store",
                "country": "IN",
                "currency": SUPPORTED_CURRENCY,
                "status": "ACTIVE",
            }
        }
        self._load_state()

    def _load_state(self):
        if not os.path.exists(STORE_PATH):
            self._save_state()
            return
        try:
            with open(STORE_PATH, encoding="utf-8") as store_file:
                state = json.load(store_file)
            self.payments.update(state.get("payments", {}))
            self.orders.update(state.get("orders", {}))
            self.transactions.update(state.get("transactions", {}))
            self.authorizations.update(state.get("authorizations", {}))
            for payment in self.payments.values():
                context = dict(DEFAULT_RISK_CONTEXT)
                context.update(payment.get("risk_context") or {})
                payment["risk_context"] = context
            for token, saved_card in state.get("cards", {}).items():
                if token in self.cards:
                    self.cards[token].update(saved_card)
        except (OSError, json.JSONDecodeError) as exc:
            LOGGER.warning("payment store could not be loaded path=%s error=%s", STORE_PATH, exc)

    def _save_state(self):
        state = {
            "payments": self.payments,
            "orders": self.orders,
            "transactions": self.transactions,
            "authorizations": self.authorizations,
            "cards": self.cards,
            "merchants": self.merchants,
        }
        directory = os.path.dirname(STORE_PATH)
        os.makedirs(directory, exist_ok=True)
        fd, temp_path = tempfile.mkstemp(prefix="payment_store_", suffix=".json", dir=directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as store_file:
                json.dump(state, store_file, indent=2)
                store_file.flush()
                os.fsync(store_file.fileno())
            os.replace(temp_path, STORE_PATH)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    @staticmethod
    def _now():
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _id(prefix):
        return f"{prefix}_{uuid4().hex[:12]}"

    def create_payment_request(self, payload):
        payload = payload or {}
        merchant_input = payload.get("merchant") or {}
        customer_input = payload.get("customer") or {}
        order_input = payload.get("order") or {}
        method = payload.get("payment_method") or {}
        merchant_id = merchant_input.get("merchant_id") or "merchant_001"
        merchant = self.merchants.get(merchant_id)
        amount = payload.get("amount")
        currency = payload.get("currency", SUPPORTED_CURRENCY)
        order_amount = order_input.get("amount", amount)
        risk_context = dict(DEFAULT_RISK_CONTEXT)
        risk_context.update(payload.get("risk_context") or {})

        if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
            raise PaymentValidationError("amount must be a positive integer in paise")
        if currency != SUPPORTED_CURRENCY:
            raise PaymentValidationError("currency must be INR")
        if not merchant or merchant["status"] != "ACTIVE":
            raise PaymentValidationError("merchant must exist and be ACTIVE")
        if not order_input.get("order_id"):
            raise PaymentValidationError("order.order_id is required")
        if order_amount != amount:
            raise PaymentValidationError("order amount must match payment amount")
        if method.get("type") != "CARD":
            raise PaymentValidationError("payment_method.type must be CARD")
        if not customer_input.get("customer_id"):
            raise PaymentValidationError("customer.customer_id is required")

        now = self._now()
        payment_id = self._id("pay")
        transaction_id = payload.get("transaction_id") or self._id("txn")
        order_id = order_input["order_id"]
        payment = {
            "payment_id": payment_id,
            "transaction_id": transaction_id,
            "order_id": order_id,
            "merchant_id": merchant_id,
            "customer_id": customer_input["customer_id"],
            "description": order_input.get("description", "Card payment"),
            "amount": amount,
            "currency": currency,
            "payment_method_type": "CARD",
            "status": "PENDING",
            "created_at": now,
            "updated_at": now,
            "reader_status": "WAITING_FOR_CARD",
            "authorization": None,
            "card": None,
            "pipeline_result": None,
            "risk_context": risk_context,
        }
        with self._lock:
            self.payments[payment_id] = payment
            self.orders[order_id] = {
                "order_id": order_id,
                "merchant_id": merchant_id,
                "customer_id": customer_input["customer_id"],
                "description": payment["description"],
                "amount": amount,
                "currency": currency,
                "status": "CREATED",
            }
            self.transactions[transaction_id] = {
                "transaction_id": transaction_id,
                "payment_id": payment_id,
                "order_id": order_id,
                "merchant_id": merchant_id,
                "customer_id": customer_input["customer_id"],
                "amount": amount,
                "currency": currency,
                "type": "PURCHASE",
                "status": "PENDING",
                "created_at": now,
            }
            self._save_state()
        self._log_event(payment, "PAYMENT_CREATED", "waiting for RFID card")
        return self.public_payment(payment)

    def get_payment(self, payment_id):
        with self._lock:
            payment = self.payments.get(payment_id)
            return self.public_payment(payment) if payment else None

    def latest_pending_payment_id(self):
        with self._lock:
            pending = [
                payment for payment in self.payments.values()
                if payment["status"] == "PENDING"
            ]
            if not pending:
                return None
            return max(pending, key=lambda payment: payment["created_at"])["payment_id"]

    def next_order_id(self):
        with self._lock:
            prefix = "order_demo_"
            numbers = []
            for order_id in self.orders:
                if not order_id.startswith(prefix):
                    continue
                try:
                    numbers.append(int(order_id[len(prefix):]))
                except ValueError:
                    continue
            return f"{prefix}{max(numbers, default=0) + 1:03d}"

    def process_card_tap(self, payment_id, rfid_token):
        token = str(rfid_token or "").strip()
        with self._lock:
            payment = self.payments.get(payment_id)
            if not payment:
                raise PaymentValidationError("payment not found")
            if payment["status"] in {"AUTHORIZED", "DECLINED", "FAILED"}:
                return self.public_payment(payment)
            self._log_event(payment, "CARD_TAP_RECEIVED", "opaque RFID token received")
            card = self.cards.get(token)
            if not card:
                return self._decline(payment, "14", "INVALID_CARD")
            payment["reader_status"] = "CARD_READ"
            payment["card"] = self._safe_card(card)
            transaction = self.transactions[payment["transaction_id"]]

            reason = self._issuer_decline_reason(card, payment["amount"])
            if reason:
                return self._decline(payment, reason[0], reason[1])

            fraud_payload = self._fraud_payload(payment, card)
            result = pipeline.run_pipeline(fraud_payload)
            payment["pipeline_result"] = result
            if result["decision"] != "APPROVE":
                return self._decline(payment, "59", "SUSPECTED_FRAUD", result)

            card["available_balance"] -= payment["amount"]
            authorization = {
                "authorization_id": self._id("auth"),
                "transaction_id": payment["transaction_id"],
                "amount": payment["amount"],
                "currency": payment["currency"],
                "status": "APPROVED",
                "response_code": "00",
                "authorization_code": uuid4().hex[:6].upper(),
                "reason": None,
                "created_at": self._now(),
            }
            self.authorizations[authorization["authorization_id"]] = authorization
            payment["authorization"] = authorization
            payment["status"] = "AUTHORIZED"
            payment["reader_status"] = "PAYMENT_AUTHORIZED"
            payment["updated_at"] = self._now()
            transaction["status"] = "AUTHORIZED"
            self.orders[payment["order_id"]]["status"] = "PAID"
            self._save_state()
            self._log_event(
                payment,
                "PAYMENT_AUTHORIZED",
                f"card={payment['card']['masked_pan']} network={payment['card']['network']}",
            )
            return self.public_payment(payment)

    @staticmethod
    def _log_event(payment, event, detail):
        LOGGER.info(
            "transaction=%s payment=%s event=%s amount_inr=%.2f amount_paise=%s status=%s detail=%s",
            payment["transaction_id"],
            payment["payment_id"],
            event,
            payment["amount"] / 100,
            payment["amount"],
            payment["status"],
            detail,
        )

    def _issuer_decline_reason(self, card, amount):
        if card["status"] != "ACTIVE":
            return "62", "CARD_BLOCKED"
        now_year = datetime.now(timezone.utc).year
        if (card["expiry_year"], card["expiry_month"]) < (now_year, datetime.now(timezone.utc).month):
            return "54", "EXPIRED_CARD"
        if card["account_status"] != "ACTIVE":
            return "62", "ACCOUNT_BLOCKED"
        if card["available_balance"] < amount:
            return "51", "INSUFFICIENT_FUNDS"
        return None

    def _fraud_payload(self, payment, card):
        now = datetime.now(timezone.utc)
        risk_context = dict(DEFAULT_RISK_CONTEXT)
        risk_context.update(payment.get("risk_context") or {})
        return {
            "transaction_id": payment["transaction_id"],
            "amount": payment["amount"] / 100,
            "hour_of_day": now.hour,
            "device_type": risk_context["device_type"],
            "merchant_category": risk_context["merchant_category"],
            "city": risk_context["city"],
            "ip_risk_score": risk_context["ip_risk_score"],
            "is_new_merchant": risk_context["is_new_merchant"],
            "distance_from_home_km": risk_context["distance_from_home_km"],
            "txn_velocity_1h": risk_context["txn_velocity_1h"],
            "avg_historical_amount": risk_context["avg_historical_amount"],
            "account_age_days": risk_context["account_age_days"],
            "network": card["network"],
        }

    def _decline(self, payment, code, reason, pipeline_result=None):
        payment["status"] = "DECLINED"
        payment["reader_status"] = "PAYMENT_DECLINED"
        payment["updated_at"] = self._now()
        payment["pipeline_result"] = pipeline_result
        self.transactions[payment["transaction_id"]]["status"] = "DECLINED"
        self.orders[payment["order_id"]]["status"] = "CREATED"
        payment["authorization"] = {
            "status": "DECLINED",
            "response_code": code,
            "reason": reason,
        }
        self._save_state()
        PaymentStore._log_event(payment, "PAYMENT_DECLINED", f"code={code} reason={reason}")
        return self.public_payment(payment)

    @staticmethod
    def _safe_card(card):
        return {
            "masked_pan": card["masked_pan"],
            "network": card["network"],
            "expiry_month": card["expiry_month"],
            "expiry_year": card["expiry_year"],
        }

    @classmethod
    def public_payment(cls, payment):
        if not payment:
            return None
        return {
            "payment_id": payment["payment_id"],
            "transaction_id": payment["transaction_id"],
            "order_id": payment["order_id"],
            "merchant_id": payment["merchant_id"],
            "customer_id": payment["customer_id"],
            "description": payment["description"],
            "amount": payment["amount"],
            "currency": payment["currency"],
            "payment_method_type": payment["payment_method_type"],
            "status": payment["status"],
            "reader_status": payment["reader_status"],
            "created_at": payment["created_at"],
            "updated_at": payment["updated_at"],
            "card": payment["card"],
            "authorization": payment["authorization"],
            "pipeline_result": payment["pipeline_result"],
            "risk_context": payment.get("risk_context", dict(DEFAULT_RISK_CONTEXT)),
        }
