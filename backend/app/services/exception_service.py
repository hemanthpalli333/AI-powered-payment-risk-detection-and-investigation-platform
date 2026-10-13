import json
from datetime import datetime
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from backend.app.database.models import Payment, BankTransaction, Invoice, Settlement, ExceptionRecord, AuditLog

class ExceptionService:
    @staticmethod
    def log_audit(db: Session, entity_type: str, entity_id: str, action: str, actor: str, details: Dict[str, Any]):
        audit = AuditLog(
            entity_type=entity_type,
            entity_id=str(entity_id),
            action=action,
            actor=actor,
            details=json.dumps(details)
        )
        db.add(audit)
        db.commit()

    @classmethod
    def create_exception(cls, db: Session, transaction_id: str, exc_type: str, diff_amt: float, evidence: Dict[str, Any]) -> ExceptionRecord:
        """Create a new exception record and audit log."""
        # Check if exception already exists for this transaction and type to avoid duplicate exception records
        existing = db.query(ExceptionRecord).filter(
            ExceptionRecord.transaction_id == transaction_id,
            ExceptionRecord.exception_type == exc_type
        ).first()
        
        if existing:
            existing.difference_amount = diff_amt
            existing.evidence = json.dumps(evidence)
            existing.status = "PENDING"
            db.commit()
            return existing

        exc = ExceptionRecord(
            transaction_id=transaction_id,
            exception_type=exc_type,
            difference_amount=diff_amt,
            evidence=json.dumps(evidence),
            status="PENDING"
        )
        db.add(exc)
        db.commit()
        db.refresh(exc)
        
        # Audit log
        cls.log_audit(
            db, 
            entity_type="exception", 
            entity_id=exc.id, 
            action="CREATE_EXCEPTION", 
            actor="exception_engine", 
            details={"transaction_id": transaction_id, "type": exc_type, "difference": diff_amt}
        )
        return exc

    @classmethod
    def detect_exceptions_for_payment(cls, db: Session, payment: Payment, bank_match: Optional[Dict[str, Any]], inv_match: Optional[Dict[str, Any]], sett_match: Optional[Dict[str, Any]]) -> bool:
        """
        Runs rules on a payment and its best matches to detect and store exceptions.
        Returns True if any exception was detected, False if fully reconciled.
        """
        transaction_id = payment.transaction_id
        has_exception = False
        
        # 1. MISSING_INVOICE
        # Payment exists, but no invoice can be matched (confidence < review threshold)
        if not inv_match or inv_match["match_confidence"] < 60.0:
            evidence = {
                "message": "Payment recorded, but no matching invoice found in system.",
                "payment": {
                    "transaction_id": payment.transaction_id,
                    "reference": payment.payment_reference,
                    "amount": payment.amount,
                    "date": payment.payment_date.strftime("%Y-%m-%d") if payment.payment_date else None
                }
            }
            cls.create_exception(db, transaction_id, "MISSING_INVOICE", payment.amount, evidence)
            has_exception = True
            db.commit()
        else:
            invoice = inv_match["matched_record"]
            invoice_id = invoice.invoice_id
            
            if invoice:
                # 2. AMOUNT_MISMATCH
                # Payment amount differs from Invoice amount
                if abs(payment.amount - invoice.invoice_amount) > 0.01:
                    diff = abs(payment.amount - invoice.invoice_amount)
                    evidence = {
                        "message": f"Payment amount of {payment.amount} does not match Invoice amount of {invoice.invoice_amount}.",
                        "payment_amount": payment.amount,
                        "invoice_amount": invoice.invoice_amount,
                        "difference": diff,
                        "invoice_id": invoice.invoice_id,
                        "invoice_reference": invoice.invoice_reference
                    }
                    cls.create_exception(db, transaction_id, "AMOUNT_MISMATCH", diff, evidence)
                    payment.status = "EXCEPTION"
                    invoice.status = "EXCEPTION"
                    has_exception = True
                    db.commit()
                    
                # 3. REFERENCE_MISMATCH
                # Reference IDs don't match exactly
                elif payment.payment_reference != invoice.invoice_reference:
                    evidence = {
                        "message": f"Payment reference '{payment.payment_reference}' differs from Invoice reference '{invoice.invoice_reference}'.",
                        "payment_reference": payment.payment_reference,
                        "invoice_reference": invoice.invoice_reference,
                        "invoice_id": invoice.invoice_id
                    }
                    cls.create_exception(db, transaction_id, "REFERENCE_MISMATCH", 0.0, evidence)
                    payment.status = "EXCEPTION"
                    invoice.status = "EXCEPTION"
                    has_exception = True
                    db.commit()

            # 4. DUPLICATE_PAYMENT
            # Check if there are other payments with the same amount and similar reference
            if inv_match and inv_match["match_confidence"] >= 60.0:
                from backend.app.services.normalization_service import NormalizationService
                
                # Fetch candidate duplicates (same amount, different ID)
                candidates = db.query(Payment).filter(
                    Payment.transaction_id != payment.transaction_id,
                    Payment.amount == payment.amount
                ).all()
                
                duplicate_payments = []
                pay_norm = NormalizationService.normalize_reference(payment.payment_reference)
                pay_core = NormalizationService.extract_core_reference(payment.payment_reference)
                
                for cand in candidates:
                    cand_norm = NormalizationService.normalize_reference(cand.payment_reference)
                    cand_core = NormalizationService.extract_core_reference(cand.payment_reference)
                    
                    if (pay_norm and cand_norm and pay_norm == cand_norm) or \
                       (pay_core and cand_core and pay_core == cand_core):
                        duplicate_payments.append(cand)
                
                if duplicate_payments:
                    dup_ids = [p.transaction_id for p in duplicate_payments]
                    evidence = {
                        "message": "Multiple payments detected with similar references and exact same amount.",
                        "invoice_id": invoice_id,
                        "duplicate_transaction_ids": dup_ids,
                        "amount": payment.amount
                    }
                    cls.create_exception(db, transaction_id, "DUPLICATE_PAYMENT", payment.amount, evidence)
                    payment.status = "EXCEPTION"
                    has_exception = True
                    db.commit()

        # 5. DATE_MISMATCH
        # Bank transaction date differs from payment date by > 5 days
        if bank_match and bank_match["match_confidence"] >= 60.0:
            btxn = bank_match["matched_record"]
            bank_id = btxn.bank_transaction_id
            if btxn and payment.payment_date and btxn.transaction_date:
                date_diff = abs((btxn.transaction_date - payment.payment_date).days)
                if date_diff > 5:
                    evidence = {
                        "message": f"Payment date ({payment.payment_date.strftime('%Y-%m-%d')}) and bank transaction date ({btxn.transaction_date.strftime('%Y-%m-%d')}) differ by {date_diff} days.",
                        "payment_date": payment.payment_date.strftime("%Y-%m-%d"),
                        "bank_transaction_date": btxn.transaction_date.strftime("%Y-%m-%d"),
                        "date_difference_days": date_diff,
                        "bank_transaction_id": bank_id
                    }
                    cls.create_exception(db, transaction_id, "DATE_MISMATCH", 0.0, evidence)
                    payment.status = "EXCEPTION"
                    btxn.status = "EXCEPTION"
                    has_exception = True
                    db.commit()

        # 6. SETTLEMENT_DISCREPANCY
        # Settlement gross amount differs, or net != gross - fee - adjustment
        if sett_match and sett_match["match_confidence"] >= 60.0:
            sett = sett_match["matched_record"]
            sett_id = sett.settlement_id
            if sett:
                expected_net = sett.gross_amount - sett.fee - sett.adjustment
                net_diff = abs(sett.net_amount - expected_net)
                gross_diff = abs(payment.amount - sett.gross_amount)
                
                if net_diff > 0.01 or gross_diff > 0.01:
                    evidence = {
                        "message": "Settlement discrepancy detected.",
                        "settlement_id": sett.settlement_id,
                        "payment_amount": payment.amount,
                        "settlement_gross": sett.gross_amount,
                        "settlement_fee": sett.fee,
                        "settlement_adjustment": sett.adjustment,
                        "settlement_net": sett.net_amount,
                        "expected_net": expected_net,
                        "net_discrepancy": net_diff,
                        "gross_discrepancy": gross_diff
                    }
                    cls.create_exception(db, transaction_id, "SETTLEMENT_DISCREPANCY", max(net_diff, gross_diff), evidence)
                    payment.status = "EXCEPTION"
                    sett.status = "EXCEPTION"
                    has_exception = True
                    db.commit()
                    
        return has_exception

    @classmethod
    def detect_missing_payments(cls, db: Session):
        """
        Runs checks to find Invoices that do not have matching Payments using full matching engine.
        """
        from backend.app.services.matching_service import MatchingService
        matching_service = MatchingService()
        
        invoices = db.query(Invoice).filter(Invoice.status == "PENDING").all()
        pending_payments = db.query(Payment).filter(Payment.status.in_(["PENDING", "UNMATCHED"])).all()
        
        for invoice in invoices:
            best_match_score = -1.0
            
            for payment in pending_payments:
                eval_res = matching_service.evaluate_pair(payment, invoice, "invoice")
                if eval_res["match_confidence"] > best_match_score:
                    best_match_score = eval_res["match_confidence"]
            
            # If even the best matching candidate falls below the review threshold (60.0), mark as missing
            if best_match_score < 60.0:
                evidence = {
                    "message": "Invoice recorded, but no acceptable payment candidate found in system.",
                    "invoice": {
                        "invoice_id": invoice.invoice_id,
                        "reference": invoice.invoice_reference,
                        "amount": invoice.invoice_amount,
                        "date": invoice.invoice_date.strftime("%Y-%m-%d") if invoice.invoice_date else None
                    }
                }
                cls.create_exception(db, invoice.invoice_id, "MISSING_PAYMENT", invoice.invoice_amount, evidence)
                invoice.status = "EXCEPTION"
                db.commit()
