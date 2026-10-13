import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from backend.app.database.database import Base

class Payment(Base):
    __tablename__ = "payments"
    
    id = Column(Integer, primary_key=True, index=True)
    transaction_id = Column(String, unique=True, index=True)
    customer_id = Column(String, index=True)
    payment_reference = Column(String, index=True)
    amount = Column(Float)
    currency = Column(String)
    payment_date = Column(DateTime)
    payment_method = Column(String)
    status = Column(String, default="PENDING")  # PENDING, RECONCILED, EXCEPTION, UNMATCHED
    
    # Original data saved for auditing/preservation
    original_reference = Column(String)
    original_amount = Column(String)

class BankTransaction(Base):
    __tablename__ = "bank_transactions"
    
    id = Column(Integer, primary_key=True, index=True)
    bank_transaction_id = Column(String, unique=True, index=True)
    bank_reference = Column(String, index=True)
    amount = Column(Float)
    transaction_date = Column(DateTime)
    description = Column(Text)
    credit_debit = Column(String)  # CREDIT, DEBIT
    bank_name = Column(String)
    status = Column(String, default="PENDING")
    
    original_reference = Column(String)
    original_amount = Column(String)

class Invoice(Base):
    __tablename__ = "invoices"
    
    id = Column(Integer, primary_key=True, index=True)
    invoice_id = Column(String, unique=True, index=True)
    customer_id = Column(String, index=True)
    invoice_reference = Column(String, index=True)
    invoice_amount = Column(Float)
    invoice_date = Column(DateTime)
    due_date = Column(DateTime)
    currency = Column(String)
    status = Column(String, default="PENDING")
    
    original_reference = Column(String)
    original_amount = Column(String)

class Settlement(Base):
    __tablename__ = "settlements"
    
    id = Column(Integer, primary_key=True, index=True)
    settlement_id = Column(String, unique=True, index=True)
    transaction_reference = Column(String, index=True)
    gross_amount = Column(Float)
    fee = Column(Float)
    adjustment = Column(Float)
    net_amount = Column(Float)
    settlement_date = Column(DateTime)
    status = Column(String, default="PENDING")
    
    original_reference = Column(String)

class ReconciliationResult(Base):
    __tablename__ = "reconciliation_results"
    
    id = Column(Integer, primary_key=True, index=True)
    transaction_id = Column(String, index=True)  # Links to payments.transaction_id
    matched_record_id = Column(String, index=True)  # Can be bank_transaction_id or invoice_id or settlement_id
    matched_record_type = Column(String)  # bank_transaction, invoice, settlement
    match_method = Column(String)  # EXACT, RULE, FUZZY, ML
    match_confidence = Column(Float)
    status = Column(String)  # AUTO_MATCH, HIGH_CONFIDENCE, REVIEW, UNMATCHED
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class ExceptionRecord(Base):
    __tablename__ = "exceptions"
    
    id = Column(Integer, primary_key=True, index=True)
    transaction_id = Column(String, index=True)  # Can link to transaction_id or invoice_id
    exception_type = Column(String, index=True)  # AMOUNT_MISMATCH, MISSING_INVOICE, etc.
    difference_amount = Column(Float, default=0.0)
    evidence = Column(Text)  # JSON string containing matching details and discrepancies
    status = Column(String, default="PENDING")  # PENDING, INVESTIGATING, RESOLVED, ESCALATED
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    investigations = relationship("Investigation", back_populates="exception_record", cascade="all, delete-orphan")
    decisions = relationship("Decision", back_populates="exception_record", cascade="all, delete-orphan")

class Investigation(Base):
    __tablename__ = "investigations"
    
    id = Column(Integer, primary_key=True, index=True)
    exception_id = Column(Integer, ForeignKey("exceptions.id"), index=True)
    summary = Column(Text)
    possible_causes = Column(Text)  # JSON array string or text
    recommendation = Column(String)  # AUTO_RECONCILE, MANUAL_REVIEW, MARK_EXCEPTION, ESCALATE
    confidence = Column(Float)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    exception_record = relationship("ExceptionRecord", back_populates="investigations")

class Decision(Base):
    __tablename__ = "decisions"
    
    id = Column(Integer, primary_key=True, index=True)
    exception_id = Column(Integer, ForeignKey("exceptions.id"), index=True)
    reviewer_id = Column(String)
    decision = Column(String)  # CONFIRM_MATCH, MARK_EXCEPTION, ESCALATE
    comments = Column(Text)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    exception_record = relationship("ExceptionRecord", back_populates="decisions")

class AuditLog(Base):
    __tablename__ = "audit_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    entity_type = Column(String, index=True)  # payment, bank_transaction, exception, decision
    entity_id = Column(String, index=True)
    action = Column(String)  # INGEST, RECONCILE, INVESTIGATE, DECIDE
    actor = Column(String)  # system, LLM_investigator, user_id
    details = Column(Text)  # JSON details or plain text
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
