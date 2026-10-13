from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.app.database.database import get_db
from backend.app.database.models import ExceptionRecord, Decision, Payment, Invoice, BankTransaction, Settlement
from backend.app.schemas.schemas import DecisionCreate, DecisionResponse
from backend.app.services.audit_service import AuditService

router = APIRouter(prefix="/decisions", tags=["Decisions"])

@router.post("/{exception_id}", response_model=DecisionResponse)
def record_decision(exception_id: int, payload: DecisionCreate, db: Session = Depends(get_db)):
    """
    Submits a human controller decision for an exception.
    Resolves the discrepancy or escalates it, auditing the action.
    """
    exception = db.query(ExceptionRecord).filter(ExceptionRecord.id == exception_id).first()
    if not exception:
        raise HTTPException(status_code=404, detail=f"Exception ID {exception_id} not found.")
        
    # Check if exception is already resolved
    if exception.status in ("RESOLVED", "ESCALATED") and payload.decision != "ESCALATE":
         raise HTTPException(status_code=400, detail=f"Exception is already in status {exception.status}.")

    # Create decision record
    decision_rec = Decision(
        exception_id=exception.id,
        reviewer_id=payload.reviewer_id,
        decision=payload.decision,
        comments=payload.comments or ""
    )
    db.add(decision_rec)
    
    # Apply business logic transitions based on decision
    if payload.decision == "CONFIRM_MATCH":
        exception.status = "RESOLVED"
        
        # Mark payment and related documents as RECONCILED since reviewer confirmed the link
        payment = db.query(Payment).filter(Payment.transaction_id == exception.transaction_id).first()
        if payment:
            payment.status = "RECONCILED"
            
            # Find bank transaction or invoice details to reconcile them
            # Check for related bank/invoice in the audit trail or references
            # As a simple fallback: find pending objects with same reference
            btxn = db.query(BankTransaction).filter(
                BankTransaction.bank_reference == payment.payment_reference,
                BankTransaction.status == "PENDING"
            ).first()
            if btxn:
                btxn.status = "RECONCILED"
                
            inv = db.query(Invoice).filter(
                Invoice.invoice_reference == payment.payment_reference,
                Invoice.status == "PENDING"
            ).first()
            if inv:
                inv.status = "RECONCILED"
                
    elif payload.decision == "MARK_EXCEPTION":
        exception.status = "RESOLVED"
        # Payment remains EXCEPTION to denote it has been verified as a true exception
        payment = db.query(Payment).filter(Payment.transaction_id == exception.transaction_id).first()
        if payment:
            payment.status = "EXCEPTION"
            
    elif payload.decision == "ESCALATE":
        exception.status = "ESCALATED"
        payment = db.query(Payment).filter(Payment.transaction_id == exception.transaction_id).first()
        if payment:
            payment.status = "EXCEPTION"
            
    else:
        raise HTTPException(status_code=400, detail="Invalid decision value. Must be CONFIRM_MATCH, MARK_EXCEPTION, or ESCALATE.")

    db.commit()
    db.refresh(decision_rec)
    
    # Audit log
    AuditService.log_event(
        db,
        entity_type="decision",
        entity_id=str(decision_rec.id),
        action="SUBMIT_DECISION",
        actor=payload.reviewer_id,
        details={
            "exception_id": exception_id,
            "decision": payload.decision,
            "comments": payload.comments
        }
    )
    
    return decision_rec
