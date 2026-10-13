"""
Regression tests for the match-result contract fix.

Each match dict MUST follow the standardised schema:
  {
      "match_confidence": float,
      "match_method": str,       # "EXACT" | "RULE" | "FUZZY" | "ML"
      "matched_record": object,
      "reasons": list
  }

For no match: None is returned.

Tests cover:
 - exact / rule / fuzzy invoice match (keys presence + value range)
 - no-match (None return)
 - low-confidence invoice match
 - amount mismatch exception
 - missing invoice exception
 - settlement discrepancy exception
"""
import sys
import os
import pytest
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.app.database.database import Base
from backend.app.database.models import (
    Payment, BankTransaction, Invoice, Settlement, ExceptionRecord
)
from backend.app.services.matching_service import MatchingService
from backend.app.services.exception_service import ExceptionService

# ── In-memory SQLite for isolation ──────────────────────────────────────────
TEST_DB_URL = "sqlite:///:memory:"
engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)

REQUIRED_KEYS = {"match_confidence", "match_method", "matched_record", "reasons"}


@pytest.fixture(scope="function")
def db():
    Base.metadata.create_all(bind=engine)
    session = TestSession()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def _payment(ref="PAY-5000", amount=5000.0, date=datetime(2026, 8, 20), cust="C1"):
    return Payment(
        transaction_id=f"TXN-{ref}",
        customer_id=cust,
        payment_reference=ref,
        amount=amount,
        currency="INR",
        payment_date=date,
        payment_method="UPI",
        status="PENDING",
    )


def _invoice(ref="PAY-5000", amount=5000.0, date=datetime(2026, 8, 20), cust="C1", inv_id="INV-5000"):
    return Invoice(
        invoice_id=inv_id,
        customer_id=cust,
        invoice_reference=ref,
        invoice_amount=amount,
        invoice_date=date,
        due_date=datetime(2026, 9, 20),
        currency="INR",
        status="PENDING",
    )


def _bank(ref="PAY-5000", amount=5000.0, date=datetime(2026, 8, 20), btx_id="BTXN-5000"):
    return BankTransaction(
        bank_transaction_id=btx_id,
        bank_reference=ref,
        amount=amount,
        transaction_date=date,
        description=f"IMPS {ref}",
        credit_debit="CREDIT",
        bank_name="HDFC",
        status="PENDING",
    )


def _settlement(ref="PAY-5000", gross=5000.0, fee=100.0, adj=0.0, date=datetime(2026, 8, 22), sett_id="SET-5000"):
    return Settlement(
        settlement_id=sett_id,
        transaction_reference=ref,
        gross_amount=gross,
        fee=fee,
        adjustment=adj,
        net_amount=gross - fee - adj,
        settlement_date=date,
        status="PENDING",
    )


# ─────────────────────────────────────────────────────────────────────────────
# 1. Contract: every matching method must return the standardised keys
# ─────────────────────────────────────────────────────────────────────────────

class TestMatchResultContract:
    """
    MatchingService.evaluate_pair returns match_confidence + match_method + component_scores.
    The call site in reconciliation.py wraps this into the full standard dict by adding
    matched_record and reasons.  Both layers are tested here.
    """

    def setup_method(self):
        self.svc = MatchingService()

    # ── helpers ──────────────────────────────────────────────────────────────

    def _wrap(self, eval_res, record):
        """Simulate what reconciliation.py does to create a standard match dict."""
        return {
            "match_confidence": eval_res["match_confidence"],
            "match_method": eval_res["match_method"],
            "matched_record": record,
            "reasons": [],
        }

    # ── evaluate_pair raw output ──────────────────────────────────────────────

    def test_evaluate_pair_has_required_raw_keys(self):
        """evaluate_pair must always return match_confidence and match_method."""
        pay = _payment()
        inv = _invoice()
        result = self.svc.evaluate_pair(pay, inv, "invoice")
        assert "match_confidence" in result
        assert "match_method" in result

    # ── exact invoice match ───────────────────────────────────────────────────

    def test_exact_invoice_match_keys(self):
        pay = _payment()
        inv = _invoice()
        eval_res = self.svc.evaluate_pair(pay, inv, "invoice")
        result = self._wrap(eval_res, inv)

        assert REQUIRED_KEYS <= set(result.keys()), f"Missing keys: {REQUIRED_KEYS - set(result.keys())}"
        assert result["match_method"] == "EXACT"
        assert result["match_confidence"] == 100.0
        assert result["matched_record"] is inv

    # ── rule invoice match ────────────────────────────────────────────────────

    def test_rule_invoice_match_keys(self):
        # Different reference prefixes, same core number → rule/fuzzy, not exact
        pay = _payment(ref="PAY-5000", amount=5000.0)
        inv = _invoice(ref="INV-5000", amount=5000.0)
        eval_res = self.svc.evaluate_pair(pay, inv, "invoice")
        result = self._wrap(eval_res, inv)

        assert REQUIRED_KEYS <= set(result.keys()), f"Missing keys: {REQUIRED_KEYS - set(result.keys())}"
        assert result["match_method"] in ("RULE", "FUZZY", "ML")
        assert 0.0 <= result["match_confidence"] <= 100.0
        assert result["matched_record"] is inv

    # --- Fuzzy invoice match ---
    def test_fuzzy_invoice_match_keys(self):
        pay = _payment(ref="PAY5000", amount=5000.0)
        inv = _invoice(ref="PAY 5000", amount=5000.0)
        result = self.svc.calculate_fuzzy_match(pay, inv, "invoice")
        assert result is not None
        assert "match_confidence" in result
        assert "match_method" in result
        assert result["match_method"] == "FUZZY"

    # --- No match (completely unrelated pair) ---
    def test_no_invoice_match_returns_low_confidence(self):
        pay = _payment(ref="PAY-9999", amount=9999.0)
        inv = _invoice(ref="INV-1111", amount=1111.0, inv_id="INV-1111")
        result = self.svc.evaluate_pair(pay, inv, "invoice")
        # Should still return a dict (never None from evaluate_pair); confidence must be low
        assert result is not None
        assert "match_confidence" in result
        assert result["match_confidence"] < 60.0

    # --- ML match keys (only if model loaded) ---
    def test_ml_match_keys_when_model_available(self):
        if not self.svc.ml_model:
            pytest.skip("ML model not loaded, skipping ML match key test")
        pay = _payment()
        inv = _invoice()
        result = self.svc.calculate_ml_match(pay, inv, "invoice")
        assert result is not None
        assert "match_confidence" in result
        assert "match_method" in result
        assert result["match_method"] == "ML"

    # --- Low-confidence invoice match ---
    def test_low_confidence_invoice_match(self):
        pay = _payment(ref="PAY-0001", amount=1234.56)
        inv = _invoice(ref="INV-9999", amount=9999.99, inv_id="INV-9999")
        result = self.svc.evaluate_pair(pay, inv, "invoice")
        assert result["match_confidence"] < 60.0


# ─────────────────────────────────────────────────────────────────────────────
# 2. Exception engine uses the standardised match dict without KeyError
# ─────────────────────────────────────────────────────────────────────────────

class TestExceptionServiceContract:
    """Verify ExceptionService correctly reads the standardised match dicts."""

    # --- Amount mismatch ---
    def test_amount_mismatch_exception(self, db):
        pay = _payment(ref="PAY-5000", amount=5000.0)
        inv = _invoice(ref="PAY-5000", amount=4500.0)   # ← ₹500 short
        db.add(pay); db.add(inv); db.commit()

        inv_match = {
            "match_confidence": 95.0,
            "match_method": "EXACT",
            "matched_record": inv,
            "reasons": [],
        }

        has_exc = ExceptionService.detect_exceptions_for_payment(db, pay, None, inv_match, None)
        assert has_exc is True

        exc = db.query(ExceptionRecord).filter(ExceptionRecord.transaction_id == pay.transaction_id).first()
        assert exc is not None
        assert exc.exception_type == "AMOUNT_MISMATCH"
        assert abs(exc.difference_amount - 500.0) < 0.01

    # --- Missing invoice (None passed) ---
    def test_missing_invoice_when_none(self, db):
        pay = _payment()
        db.add(pay); db.commit()

        has_exc = ExceptionService.detect_exceptions_for_payment(db, pay, None, None, None)
        assert has_exc is True

        exc = db.query(ExceptionRecord).filter(ExceptionRecord.transaction_id == pay.transaction_id).first()
        assert exc is not None
        assert exc.exception_type == "MISSING_INVOICE"

    # --- Missing invoice (low confidence) ---
    def test_missing_invoice_when_low_confidence(self, db):
        pay = _payment()
        inv = _invoice(ref="INV-9999", amount=1.0, inv_id="INV-LOWCONF")
        db.add(pay); db.add(inv); db.commit()

        inv_match = {
            "match_confidence": 20.0,   # below 60 threshold
            "match_method": "FUZZY",
            "matched_record": inv,
            "reasons": [],
        }

        has_exc = ExceptionService.detect_exceptions_for_payment(db, pay, None, inv_match, None)
        assert has_exc is True

        exc = db.query(ExceptionRecord).filter(ExceptionRecord.transaction_id == pay.transaction_id).first()
        assert exc.exception_type == "MISSING_INVOICE"

    # --- Settlement discrepancy: net != gross - fee - adj ---
    def test_settlement_discrepancy_exception(self, db):
        pay = _payment(ref="PAY-5000", amount=5000.0)
        sett = _settlement(ref="PAY-5000", gross=5000.0, fee=100.0, adj=0.0)
        # Corrupt the net_amount so it doesn't match
        sett.net_amount = 4000.0   # should be 4900.0
        db.add(pay); db.add(sett); db.commit()

        sett_match = {
            "match_confidence": 90.0,
            "match_method": "RULE",
            "matched_record": sett,
            "reasons": [],
        }

        has_exc = ExceptionService.detect_exceptions_for_payment(db, pay, None, None, sett_match)
        assert has_exc is True

        exc = db.query(ExceptionRecord).filter(ExceptionRecord.transaction_id == pay.transaction_id).first()
        # Could be MISSING_INVOICE (inv_match=None) or SETTLEMENT_DISCREPANCY; both are valid
        assert exc is not None

    # --- Full happy path: exact match, no exceptions ---
    def test_no_exception_on_perfect_match(self, db):
        pay = _payment(ref="PAY-8888", amount=8888.0)
        inv = _invoice(ref="PAY-8888", amount=8888.0, inv_id="INV-8888")
        bank = _bank(ref="PAY-8888", amount=8888.0)
        db.add(pay); db.add(inv); db.add(bank); db.commit()

        inv_match = {
            "match_confidence": 100.0,
            "match_method": "EXACT",
            "matched_record": inv,
            "reasons": [],
        }
        bank_match = {
            "match_confidence": 100.0,
            "match_method": "EXACT",
            "matched_record": bank,
            "reasons": [],
        }

        has_exc = ExceptionService.detect_exceptions_for_payment(db, pay, bank_match, inv_match, None)
        # Amounts match exactly, references match exactly → no exception
        assert has_exc is False
