import time
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional

from backend.app.database.database import get_db
from backend.app.database.models import Payment, BankTransaction, Invoice, Settlement, ReconciliationResult, ExceptionRecord
from backend.app.schemas.schemas import ReconciliationRunRequest, ReconciliationRunResult, ReconciliationSummary, ReconciliationResultResponse
from backend.app.services.matching_service import MatchingService
from backend.app.services.scoring_service import ScoringService
from backend.app.services.exception_service import ExceptionService
from backend.app.services.audit_service import AuditService

router = APIRouter(prefix="/reconciliation", tags=["Reconciliation"])
matching_service = MatchingService()

@router.post("/run", response_model=ReconciliationRunResult)
def run_reconciliation(
    payload: Optional[ReconciliationRunRequest] = None,
    db: Session = Depends(get_db)
):
    """
    Executes the reconciliation engine on all PENDING payment records.
    Matches them against bank transactions, invoices, and settlements.
    """
    start_time = time.time()
    
    # Reload ML Model in matching service if it wasn't loaded
    if not matching_service.ml_model:
        matching_service.load_ml_model()

    # Fetch thresholds
    auto_thresh = payload.auto_match_thresh if payload else None
    high_thresh = payload.high_conf_thresh if payload else None
    rev_thresh = payload.review_thresh if payload else None
    
    # 1. Fetch pending records
    pending_payments = db.query(Payment).filter(Payment.status.in_(["PENDING", "UNMATCHED"])).all()
    pending_bank = db.query(BankTransaction).filter(BankTransaction.status.in_(["PENDING", "UNMATCHED"])).all()
    pending_invoices = db.query(Invoice).filter(Invoice.status.in_(["PENDING", "UNMATCHED"])).all()
    pending_settlements = db.query(Settlement).filter(Settlement.status.in_(["PENDING", "UNMATCHED"])).all()
    
    # 2. Build blocks/indexes to avoid O(P x B) full Cartesian comparisons
    from collections import defaultdict
    
    bank_blocks = defaultdict(list)
    for b in pending_bank: bank_blocks[round(b.amount / 1000)].append(b)
        
    inv_blocks = defaultdict(list)
    for i in pending_invoices: inv_blocks[round(i.invoice_amount / 1000)].append(i)
        
    sett_blocks = defaultdict(list)
    for s in pending_settlements: sett_blocks[round(s.gross_amount / 1000)].append(s)

    total_processed = len(pending_payments)
    auto_matched = 0
    exceptions_detected = 0
    unmatched_count = 0
    
    # 3. Iterate through pending payments (O(P x Block Size))
    for payment in pending_payments:
        pay_bin = round(payment.amount / 1000)
        
        # Fetch candidates from the current and adjacent bins (+/- 1000 margin)
        cand_banks = bank_blocks[pay_bin] + bank_blocks[pay_bin - 1] + bank_blocks[pay_bin + 1]
        cand_invs = inv_blocks[pay_bin] + inv_blocks[pay_bin - 1] + inv_blocks[pay_bin + 1]
        cand_setts = sett_blocks[pay_bin] + sett_blocks[pay_bin - 1] + sett_blocks[pay_bin + 1]
        
        # Match against Bank Transactions
        best_bank_match = None
        best_bank_score = -1.0
        for bank in cand_banks:
            eval_res = matching_service.evaluate_pair(payment, bank, "bank_transaction")
            if eval_res["match_confidence"] > best_bank_score:
                best_bank_score = eval_res["match_confidence"]
                best_bank_match = {
                    "match_confidence": best_bank_score,
                    "match_method": eval_res["match_method"],
                    "matched_record": bank,
                    "reasons": []
                }
                
        # Match against Invoices
        best_inv_match = None
        best_inv_score = -1.0
        for invoice in cand_invs:
            eval_res = matching_service.evaluate_pair(payment, invoice, "invoice")
            if eval_res["match_confidence"] > best_inv_score:
                best_inv_score = eval_res["match_confidence"]
                best_inv_match = {
                    "match_confidence": best_inv_score,
                    "match_method": eval_res["match_method"],
                    "matched_record": invoice,
                    "reasons": []
                }
                
        # Match against Settlements
        best_sett_match = None
        best_sett_score = -1.0
        for settlement in cand_setts:
            eval_res = matching_service.evaluate_pair(payment, settlement, "settlement")
            if eval_res["match_confidence"] > best_sett_score:
                best_sett_score = eval_res["match_confidence"]
                best_sett_match = {
                    "match_confidence": best_sett_score,
                    "match_method": eval_res["match_method"],
                    "matched_record": settlement,
                    "reasons": []
                }

        # Save reconciliation candidate result
        res = ReconciliationResult(
            transaction_id=payment.transaction_id,
            matched_record_id=best_bank_match["matched_record"].bank_transaction_id if best_bank_match else "None",
            matched_record_type="bank_transaction" if best_bank_match else "None",
            match_method=best_bank_match["match_method"] if best_bank_match else "None",
            match_confidence=best_bank_score,
            status="PENDING_VALIDATION"
        )
        db.add(res)
        db.commit()

        # Determine match path based on bank match (primary clearing event)
        status_category = ScoringService.get_match_status(best_bank_score, auto_thresh, high_thresh, rev_thresh)
        
        if status_category in ("AUTO_MATCH", "HIGH_CONFIDENCE", "REVIEW"):
            # Run Exception Engine to classify and log the discrepancies
            has_exception = ExceptionService.detect_exceptions_for_payment(
                db=db,
                payment=payment,
                bank_match=best_bank_match,
                inv_match=best_inv_match,
                sett_match=best_sett_match
            )
            
            if has_exception:
                res.status = "EXCEPTION"
                exceptions_detected += 1
            elif status_category in ("AUTO_MATCH", "HIGH_CONFIDENCE"):
                # Reconciled! No financial discrepancy and high enough confidence
                res.status = "AUTO_MATCH"
                payment.status = "RECONCILED"
                best_bank_match["matched_record"].status = "RECONCILED"
                
                if best_inv_match and best_inv_match["match_confidence"] >= 60.0:
                    best_inv_match["matched_record"].status = "RECONCILED"
                if best_sett_match and best_sett_match["match_confidence"] >= 60.0:
                    best_sett_match["matched_record"].status = "RECONCILED"
                    
                AuditService.log_event(
                    db,
                    entity_type="payment",
                    entity_id=payment.transaction_id,
                    action="AUTO_RECONCILE",
                    actor="reconciliation_engine",
                    details={
                        "bank_transaction_id": best_bank_match["matched_record"].bank_transaction_id,
                        "confidence": best_bank_score,
                        "method": best_bank_match["match_method"]
                    }
                )
                auto_matched += 1
            else:
                # Valid but too low confidence, mark for review
                res.status = "REVIEW"
                payment.status = "EXCEPTION"
                ExceptionService.create_exception(
                    db, payment.transaction_id, "LOW_CONFIDENCE", 0.0,
                    {"message": f"Match confidence {best_bank_score}% is too low for auto-reconciliation."}
                )
                exceptions_detected += 1
        else:
            # Unmatched record
            payment.status = "UNMATCHED"
            res.status = "UNMATCHED"
            AuditService.log_event(
                db,
                entity_type="payment",
                entity_id=payment.transaction_id,
                action="MARK_UNMATCHED",
                actor="reconciliation_engine",
                details={"best_bank_score": best_bank_score}
            )
            unmatched_count += 1
            
        db.commit()
            
    # Also scan for missing payment exceptions (Invoices with no matching payments)
    ExceptionService.detect_missing_payments(db)
    
    elapsed_time = time.time() - start_time
    
    # Audit bulk execution
    AuditService.log_event(
        db,
        entity_type="reconciliation",
        entity_id="run",
        action="RUN_ENGINE",
        actor="system",
        details={
            "total_processed": total_processed,
            "auto_matched": auto_matched,
            "exceptions_detected": exceptions_detected,
            "unmatched": unmatched_count
        }
    )
    
    return ReconciliationRunResult(
        total_processed=total_processed,
        auto_matched=auto_matched,
        exceptions_detected=exceptions_detected,
        unmatched=unmatched_count,
        execution_time_seconds=round(elapsed_time, 3)
    )


@router.get("/summary", response_model=ReconciliationSummary)
def get_reconciliation_summary(db: Session = Depends(get_db)):
    """
    Computes real financial reconciliation stats across payments, exceptions, etc.
    """
    total_payments = db.query(Payment).count()
    auto_reconciled = db.query(Payment).filter(Payment.status == "RECONCILED").count()
    
    # Exceptions that are still unresolved (PENDING or INVESTIGATING)
    pending_review = db.query(ExceptionRecord).filter(ExceptionRecord.status.in_(["PENDING", "INVESTIGATING"])).count()
    
    unmatched = db.query(Payment).filter(Payment.status == "UNMATCHED").count()
    
    # Aggregate outstanding exception values
    exception_value_res = db.query(ExceptionRecord).filter(
        ExceptionRecord.status.in_(["PENDING", "INVESTIGATING"])
    ).all()
    exception_value = sum(exc.difference_amount for exc in exception_value_res)
    
    reconciliation_rate = (auto_reconciled / total_payments * 100.0) if total_payments > 0 else 0.0
    auto_match_rate = reconciliation_rate # for our current logic, auto matched == reconciled
    
    return ReconciliationSummary(
        total_payments=total_payments,
        auto_reconciled=auto_reconciled,
        pending_review=pending_review,
        unmatched=unmatched,
        exception_value=round(exception_value, 2),
        reconciliation_rate=round(reconciliation_rate, 2),
        auto_match_rate=round(auto_match_rate, 2)
    )


@router.get("/{transaction_id}", response_model=List[ReconciliationResultResponse])
def get_reconciliation_details(transaction_id: str, db: Session = Depends(get_db)):
    """
    Retrieves match history / results for a specific transaction.
    """
    results = db.query(ReconciliationResult).filter(ReconciliationResult.transaction_id == transaction_id).all()
    if not results:
        raise HTTPException(status_code=404, detail=f"No reconciliation results found for transaction {transaction_id}")
    return results
