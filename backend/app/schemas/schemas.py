from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime

# --- Ingestion Schemas ---

class PaymentCreate(BaseModel):
    transaction_id: str = Field(..., description="Unique transaction ID from payment system")
    customer_id: str = Field(..., description="Unique customer ID")
    payment_reference: str = Field(..., description="Payment Reference string")
    amount: Any = Field(..., description="Payment Amount (float or formatted string)")
    currency: str = Field(default="INR", description="Currency (3 letters)")
    payment_date: str = Field(..., description="Payment date string (YYYY-MM-DD)")
    payment_method: str = Field(default="UPI", description="UPI, NetBanking, Card, etc.")

class BankTransactionCreate(BaseModel):
    bank_transaction_id: str = Field(..., description="Transaction ID from bank statement")
    bank_reference: str = Field(..., description="Bank reference number")
    amount: float = Field(..., description="Amount credited/debited")
    transaction_date: str = Field(..., description="Transaction Date/Time")
    description: str = Field(..., description="Transaction narration/description")
    credit_debit: str = Field(default="CREDIT", description="CREDIT or DEBIT")
    bank_name: str = Field(..., description="Bank Name")

class InvoiceCreate(BaseModel):
    invoice_id: str = Field(..., description="Unique Invoice ID")
    customer_id: str = Field(..., description="Customer ID associated with invoice")
    invoice_reference: str = Field(..., description="Invoice reference string")
    invoice_amount: float = Field(..., description="Total Invoice Amount")
    invoice_date: str = Field(..., description="Invoice creation date (YYYY-MM-DD)")
    due_date: str = Field(..., description="Invoice payment due date")
    currency: str = Field(default="INR", description="Currency")

class SettlementCreate(BaseModel):
    settlement_id: str = Field(..., description="Unique Settlement ID")
    transaction_reference: str = Field(..., description="Reference ID matching payment transaction")
    gross_amount: float = Field(..., description="Gross settled amount")
    fee: float = Field(default=0.0, description="Processing fees")
    adjustment: float = Field(default=0.0, description="Gateway adjustment / refund / chargeback")
    net_amount: float = Field(..., description="Net settled amount received in bank")
    settlement_date: str = Field(..., description="Settlement date (YYYY-MM-DD)")

# --- Ingestion Batch Responses ---

class IngestionResponse(BaseModel):
    status: str = "success"
    processed_count: int
    inserted_count: int
    errors: List[Dict[str, Any]] = []

# --- Reconciliation Run & Summary Schemas ---

class ReconciliationRunRequest(BaseModel):
    auto_match_thresh: Optional[float] = None
    high_conf_thresh: Optional[float] = None
    review_thresh: Optional[float] = None

class ReconciliationRunResult(BaseModel):
    status: str = "success"
    total_processed: int
    auto_matched: int
    exceptions_detected: int
    unmatched: int
    execution_time_seconds: float

class ReconciliationSummary(BaseModel):
    total_payments: int
    auto_reconciled: int
    pending_review: int
    unmatched: int
    exception_value: float
    reconciliation_rate: float
    auto_match_rate: float

class ReconciliationResultResponse(BaseModel):
    id: int
    transaction_id: str
    matched_record_id: str
    matched_record_type: str
    match_method: str
    match_confidence: float
    status: str
    created_at: datetime

    class Config:
        from_attributes = True

# --- Exception Schemas ---

class ExceptionResponse(BaseModel):
    id: int
    transaction_id: str
    exception_type: str
    difference_amount: float
    evidence: Any # parsed JSON
    status: str
    created_at: datetime

    class Config:
        from_attributes = True

# --- AI Investigation Schemas ---

class InvestigationResponse(BaseModel):
    id: int
    exception_id: int
    summary: str
    possible_causes: List[str]
    recommendation: str
    confidence: float
    created_at: datetime

    class Config:
        from_attributes = True

# --- Human Decision Schemas ---

class DecisionCreate(BaseModel):
    reviewer_id: str = Field(..., description="Username/ID of reviewer")
    decision: str = Field(..., description="CONFIRM_MATCH, MARK_EXCEPTION, or ESCALATE")
    comments: Optional[str] = Field(None, description="Reviewer feedback")

class DecisionResponse(BaseModel):
    id: int
    exception_id: int
    reviewer_id: str
    decision: str
    comments: str
    created_at: datetime

    class Config:
        from_attributes = True

# --- Audit Logs ---

class AuditLogResponse(BaseModel):
    id: int
    entity_type: str
    entity_id: str
    action: str
    actor: str
    details: Any # parsed JSON
    created_at: datetime

    class Config:
        from_attributes = True

# --- Finance Copilot Schemas ---

class CopilotQueryRequest(BaseModel):
    query: str = Field(..., description="Natural language prompt for copilot")

class CopilotResponse(BaseModel):
    answer: str
    query_results: Optional[List[Dict[str, Any]]] = None

# --- Monitoring & Quality Schemas ---

class DataQualityReport(BaseModel):
    total_records: int
    missing_fields: int
    duplicate_records: int
    invalid_amounts: int
    invalid_dates: int
    currency_inconsistencies: int

class MonitoringReport(BaseModel):
    data_quality: DataQualityReport
    match_rate: float
    auto_match_rate: float
    manual_review_rate: float
    unmatched_rate: float
    exception_rate: float
    drift_status: str # HEALTHY, DRIFT_DETECTED, REVIEW_REQUIRED
    drift_details: Dict[str, Any]
