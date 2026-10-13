import sys
import os
import pytest
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.app.database.database import Base
from backend.app.database.models import Payment, BankTransaction, Invoice, Settlement, ExceptionRecord, ReconciliationResult, Investigation, Decision, AuditLog
from backend.app.services.normalization_service import NormalizationService
from backend.app.services.matching_service import MatchingService
from backend.app.services.scoring_service import ScoringService
from backend.app.services.exception_service import ExceptionService
from backend.app.services.investigation_agent import InvestigationAgent

# Setup a clean SQLite in-memory database for testing
TEST_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="function")
def db_session():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)

# --- Unit Tests: Normalization ---

def test_amount_normalization():
    assert NormalizationService.normalize_amount("₹12,450") == 12450.0
    assert NormalizationService.normalize_amount("12450.00") == 12450.0
    assert NormalizationService.normalize_amount("12,450 INR") == 12450.0
    assert NormalizationService.normalize_amount("12.450,00") == 12450.0 # European format
    assert NormalizationService.normalize_amount(-150.0) == -150.0
    assert NormalizationService.normalize_amount(None) == 0.0

def test_date_normalization():
    assert NormalizationService.normalize_date("2026-08-20") == datetime(2026, 8, 20)
    assert NormalizationService.normalize_date("2026-08-20 14:30:00") == datetime(2026, 8, 20, 14, 30)
    assert NormalizationService.normalize_date("20/08/2026") == datetime(2026, 8, 20)
    assert NormalizationService.normalize_date(None) is None

def test_reference_normalization():
    assert NormalizationService.normalize_reference("PAY-0008921") == "pay8921"
    assert NormalizationService.normalize_reference("pay-8921") == "pay8921"
    assert NormalizationService.normalize_reference("PAY8921") == "pay8921"
    assert NormalizationService.normalize_reference(None) == ""

def test_core_reference_extraction():
    assert NormalizationService.extract_core_reference("PAY-8921") == "8921"
    assert NormalizationService.extract_core_reference("BANK-8921") == "8921"
    assert NormalizationService.extract_core_reference("REF-004455") == "4455"

# --- Unit Tests: Matching Engine ---

def test_exact_matching():
    matching_service = MatchingService()
    
    payment = Payment(amount=5000.0, payment_reference="REF-1001", payment_date=datetime(2026, 8, 20))
    bank = BankTransaction(amount=5000.0, bank_reference="REF-1001", transaction_date=datetime(2026, 8, 20))
    
    # Exact Match Level 1
    match_res = matching_service.calculate_exact_match(payment, bank, "bank_transaction")
    assert match_res is not None
    assert match_res["match_method"] == "EXACT"
    assert match_res["match_confidence"] == 100.0

def test_fuzzy_and_rule_matching():
    matching_service = MatchingService()
    
    # reference mismatch: PAY-8921 vs BANK-8921
    payment = Payment(amount=12450.0, payment_reference="PAY-8921", payment_date=datetime(2026, 8, 28), customer_id="CUST2")
    bank = BankTransaction(amount=12450.0, bank_reference="BANK-8921", transaction_date=datetime(2026, 8, 28), description="IMPS REF:BANK-8921 FROM CUST2")
    
    # Exact should fail
    exact_res = matching_service.calculate_exact_match(payment, bank, "bank_transaction")
    assert exact_res is None
    
    # Rule/Fuzzy/ML should succeed with high score (since amount and date match, and core reference matches)
    pair_res = matching_service.evaluate_pair(payment, bank, "bank_transaction")
    assert pair_res["match_confidence"] >= 80.0
    assert pair_res["match_method"] in ("RULE", "FUZZY", "ML")

# --- Unit Tests: Exceptions ---

def test_exception_detection(db_session):
    # Setup amount mismatch
    payment = Payment(transaction_id="TXN_TEST_1", amount=12450.0, payment_reference="PAY-8921", payment_date=datetime(2026, 8, 28), customer_id="CUST1")
    invoice = Invoice(invoice_id="INV-8921", invoice_reference="PAY-8921", invoice_amount=12000.0, invoice_date=datetime(2026, 8, 27), due_date=datetime(2026, 9, 10), customer_id="CUST1")
    
    db_session.add(payment)
    db_session.add(invoice)
    db_session.commit()
    
    inv_match = {
        "match_confidence": 92.0,
        "match_method": "RULE",
        "matched_record": invoice,
        "reasons": []
    }
    ExceptionService.detect_exceptions_for_payment(db_session, payment, None, inv_match, None)
    
    # Verify exception is logged
    exc = db_session.query(ExceptionRecord).filter(ExceptionRecord.transaction_id == "TXN_TEST_1").first()
    assert exc is not None
    assert exc.exception_type == "AMOUNT_MISMATCH"
    assert exc.difference_amount == 450.0
    assert payment.status == "EXCEPTION"

# --- End to End Integration Test ---

def test_end_to_end_flow(db_session):
    # 1. Ingest Data
    payment = Payment(
        transaction_id="TXN1021",
        customer_id="CUST2001",
        payment_reference="PAY-8921",
        amount=12450.0,
        currency="INR",
        payment_date=datetime(2026, 8, 28),
        payment_method="IMPS",
        status="PENDING"
    )
    bank = BankTransaction(
        bank_transaction_id="BTXN1021",
        bank_reference="BANK-8921",
        amount=12450.0,
        transaction_date=datetime(2026, 8, 28, 14, 0),
        description="IMPS REF:BANK-8921 FROM CUST2001",
        credit_debit="CREDIT",
        bank_name="ICICI Bank",
        status="PENDING"
    )
    invoice = Invoice(
        invoice_id="INV-8921",
        customer_id="CUST2001",
        invoice_reference="INV-8921",
        invoice_amount=12000.0,
        invoice_date=datetime(2026, 8, 27),
        due_date=datetime(2026, 9, 10),
        currency="INR",
        status="PENDING"
    )
    settlement = Settlement(
        settlement_id="SET-1021",
        transaction_reference="PAY-8921",
        gross_amount=12450.0,
        fee=250.0,
        adjustment=0.0,
        net_amount=12200.0,
        settlement_date=datetime(2026, 8, 30),
        status="PENDING"
    )
    
    db_session.add_all([payment, bank, invoice, settlement])
    db_session.commit()
    
    # 2. Run Reconciliation Simulation (simulate code inside API)
    matching_service = MatchingService()
    
    # Bank matches on rule/fuzzy because of reference format (PAY-8921 vs BANK-8921)
    eval_bank = matching_service.evaluate_pair(payment, bank, "bank_transaction")
    bank_match = {
        "match_confidence": eval_bank["match_confidence"],
        "match_method": eval_bank["match_method"],
        "matched_record": bank,
        "reasons": []
    }
    
    # Invoice matches because reference PAY-8921 and INV-8921 both have core numeric 8921
    eval_inv = matching_service.evaluate_pair(payment, invoice, "invoice")
    inv_match = {
        "match_confidence": eval_inv["match_confidence"],
        "match_method": eval_inv["match_method"],
        "matched_record": invoice,
        "reasons": []
    }
    
    # Settlement matches because reference PAY-8921
    eval_sett = matching_service.evaluate_pair(payment, settlement, "settlement")
    sett_match = {
        "match_confidence": eval_sett["match_confidence"],
        "match_method": eval_sett["match_method"],
        "matched_record": settlement,
        "reasons": []
    }
    
    # Since bank_match is rule-based and not 100% exact, it goes to Exception detection
    ExceptionService.detect_exceptions_for_payment(db_session, payment, bank_match, inv_match, sett_match)
    
    # Verify exception created
    exc = db_session.query(ExceptionRecord).filter(ExceptionRecord.transaction_id == "TXN1021").first()
    assert exc is not None
    assert exc.exception_type == "AMOUNT_MISMATCH"
    
    # 3. Trigger Investigation
    investigation = InvestigationAgent.investigate_exception(db_session, exc.id)
    assert investigation is not None
    assert investigation.exception_id == exc.id
    assert investigation.recommendation == "MANUAL_REVIEW"
    assert exc.status == "INVESTIGATING"
    
    # 4. Reviewer Decision
    decision_rec = Decision(
        exception_id=exc.id,
        reviewer_id="finance_controller_test",
        decision="MARK_EXCEPTION",
        comments="Checked ledger, confirmed ₹450 invoice discrepancy as adjustment exception."
    )
    db_session.add(decision_rec)
    exc.status = "RESOLVED"
    payment.status = "EXCEPTION" # keep as verified exception
    db_session.commit()
    
    # Log Audit
    audit = AuditLog(
        entity_type="decision",
        entity_id=str(decision_rec.id),
        action="SUBMIT_DECISION",
        actor="finance_controller_test",
        details="{'decision': 'MARK_EXCEPTION'}"
    )
    db_session.add(audit)
    db_session.commit()
    
    # Verify states
    assert exc.status == "RESOLVED"
    assert payment.status == "EXCEPTION"
    
    recent_audit = db_session.query(AuditLog).filter(AuditLog.actor == "finance_controller_test").first()
    assert recent_audit is not None
