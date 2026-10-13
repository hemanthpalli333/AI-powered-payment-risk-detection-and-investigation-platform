import io
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from typing import List, Optional

from backend.app.database.database import get_db
from backend.app.database.models import Payment, BankTransaction, Invoice, Settlement, AuditLog
from backend.app.schemas.schemas import IngestionResponse
from backend.app.services.normalization_service import NormalizationService
from backend.app.services.audit_service import AuditService

router = APIRouter(prefix="/ingestion", tags=["Ingestion"])

@router.post("/payments", response_model=IngestionResponse)
async def ingest_payments(
    file: Optional[UploadFile] = File(None),
    payments: Optional[List[dict]] = None,
    db: Session = Depends(get_db)
):
    """
    Ingest payment records via CSV file upload or JSON payload.
    """
    records = []
    if file:
        try:
            content = await file.read()
            df = pd.read_csv(io.BytesIO(content))
            records = df.to_dict(orient="records")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to parse CSV file: {e}")
    elif payments is not None:
        records = payments
    else:
        raise HTTPException(status_code=400, detail="Provide either a CSV file or JSON list of payments.")

    processed = 0
    inserted = 0
    errors = []
    
    required_cols = {"transaction_id", "customer_id", "payment_reference", "amount", "payment_date"}
    
    for idx, row in enumerate(records):
        # Validate columns
        missing = required_cols - set(row.keys())
        if missing:
            errors.append({"row": idx, "error": f"Missing columns: {missing}"})
            continue
            
        tx_id = str(row["transaction_id"]).strip()
        
        # Check if already exists
        existing = db.query(Payment).filter(Payment.transaction_id == tx_id).first()
        if existing:
            # Quietly skip duplicates to avoid UI error spam on re-uploads
            processed += 1
            continue
            
        try:
            # Normalize inputs
            orig_ref = row["payment_reference"]
            orig_amt = row["amount"]
            
            clean_amt = NormalizationService.normalize_amount(orig_amt)
            clean_date = NormalizationService.normalize_date(row["payment_date"])
            
            if not clean_date:
                errors.append({"row": idx, "error": f"Invalid payment_date: {row['payment_date']}"})
                continue
                
            payment = Payment(
                transaction_id=tx_id,
                customer_id=str(row["customer_id"]).strip(),
                payment_reference=str(orig_ref).strip(),
                amount=clean_amt,
                currency=str(row.get("currency", "INR")).strip().upper(),
                payment_date=clean_date,
                payment_method=str(row.get("payment_method", "UPI")).strip(),
                status="PENDING",
                original_reference=str(orig_ref),
                original_amount=str(orig_amt)
            )
            db.add(payment)
            inserted += 1
        except Exception as e:
            errors.append({"row": idx, "error": f"Error inserting record: {e}"})
        
        processed += 1
        
    db.commit()
    
    if inserted > 0:
        AuditService.log_event(
            db,
            entity_type="payments",
            entity_id="bulk_ingest",
            action="INGEST_PAYMENTS",
            actor="system",
            details={"inserted": inserted, "errors_count": len(errors)}
        )
        
    return IngestionResponse(processed_count=processed, inserted_count=inserted, errors=errors)


@router.post("/bank-statements", response_model=IngestionResponse)
async def ingest_bank_statements(
    file: Optional[UploadFile] = File(None),
    transactions: Optional[List[dict]] = None,
    db: Session = Depends(get_db)
):
    """
    Ingest bank statement transactions via CSV file upload or JSON payload.
    """
    records = []
    if file:
        try:
            content = await file.read()
            df = pd.read_csv(io.BytesIO(content))
            records = df.to_dict(orient="records")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to parse CSV file: {e}")
    elif transactions is not None:
        records = transactions
    else:
        raise HTTPException(status_code=400, detail="Provide either a CSV file or JSON list of transactions.")

    processed = 0
    inserted = 0
    errors = []
    
    required_cols = {"bank_transaction_id", "bank_reference", "amount", "transaction_date", "description", "bank_name"}
    
    for idx, row in enumerate(records):
        missing = required_cols - set(row.keys())
        if missing:
            errors.append({"row": idx, "error": f"Missing columns: {missing}"})
            continue
            
        btx_id = str(row["bank_transaction_id"]).strip()
        
        existing = db.query(BankTransaction).filter(BankTransaction.bank_transaction_id == btx_id).first()
        if existing:
            processed += 1
            continue
            
        try:
            orig_ref = row["bank_reference"]
            orig_amt = row["amount"]
            
            clean_amt = NormalizationService.normalize_amount(orig_amt)
            clean_date = NormalizationService.normalize_date(row["transaction_date"])
            
            if not clean_date:
                errors.append({"row": idx, "error": f"Invalid transaction_date: {row['transaction_date']}"})
                continue
                
            btxn = BankTransaction(
                bank_transaction_id=btx_id,
                bank_reference=str(orig_ref).strip(),
                amount=clean_amt,
                transaction_date=clean_date,
                description=str(row["description"]),
                credit_debit=str(row.get("credit_debit", "CREDIT")).strip().upper(),
                bank_name=str(row["bank_name"]).strip(),
                status="PENDING",
                original_reference=str(orig_ref),
                original_amount=str(orig_amt)
            )
            db.add(btxn)
            inserted += 1
        except Exception as e:
            errors.append({"row": idx, "error": f"Error inserting record: {e}"})
            
        processed += 1
        
    db.commit()
    
    if inserted > 0:
        AuditService.log_event(
            db,
            entity_type="bank_transactions",
            entity_id="bulk_ingest",
            action="INGEST_BANK_TRANSACTIONS",
            actor="system",
            details={"inserted": inserted, "errors_count": len(errors)}
        )
        
    return IngestionResponse(processed_count=processed, inserted_count=inserted, errors=errors)


@router.post("/invoices", response_model=IngestionResponse)
async def ingest_invoices(
    file: Optional[UploadFile] = File(None),
    invoices: Optional[List[dict]] = None,
    db: Session = Depends(get_db)
):
    """
    Ingest invoice records via CSV file upload or JSON payload.
    """
    records = []
    if file:
        try:
            content = await file.read()
            df = pd.read_csv(io.BytesIO(content))
            records = df.to_dict(orient="records")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to parse CSV file: {e}")
    elif invoices is not None:
        records = invoices
    else:
        raise HTTPException(status_code=400, detail="Provide either a CSV file or JSON list of invoices.")

    processed = 0
    inserted = 0
    errors = []
    
    required_cols = {"invoice_id", "customer_id", "invoice_reference", "invoice_amount", "invoice_date", "due_date"}
    
    for idx, row in enumerate(records):
        missing = required_cols - set(row.keys())
        if missing:
            errors.append({"row": idx, "error": f"Missing columns: {missing}"})
            continue
            
        inv_id = str(row["invoice_id"]).strip()
        
        existing = db.query(Invoice).filter(Invoice.invoice_id == inv_id).first()
        if existing:
            processed += 1
            continue
            
        try:
            orig_ref = row["invoice_reference"]
            orig_amt = row["invoice_amount"]
            
            clean_amt = NormalizationService.normalize_amount(orig_amt)
            clean_date = NormalizationService.normalize_date(row["invoice_date"])
            clean_due = NormalizationService.normalize_date(row["due_date"])
            
            if not clean_date or not clean_due:
                errors.append({"row": idx, "error": "Invalid date format in invoice_date or due_date"})
                continue
                
            inv = Invoice(
                invoice_id=inv_id,
                customer_id=str(row["customer_id"]).strip(),
                invoice_reference=str(orig_ref).strip(),
                invoice_amount=clean_amt,
                invoice_date=clean_date,
                due_date=clean_due,
                currency=str(row.get("currency", "INR")).strip().upper(),
                status="PENDING",
                original_reference=str(orig_ref),
                original_amount=str(orig_amt)
            )
            db.add(inv)
            inserted += 1
        except Exception as e:
            errors.append({"row": idx, "error": f"Error inserting record: {e}"})
            
        processed += 1
        
    db.commit()
    
    if inserted > 0:
        AuditService.log_event(
            db,
            entity_type="invoices",
            entity_id="bulk_ingest",
            action="INGEST_INVOICES",
            actor="system",
            details={"inserted": inserted, "errors_count": len(errors)}
        )
        
    return IngestionResponse(processed_count=processed, inserted_count=inserted, errors=errors)


@router.post("/settlements", response_model=IngestionResponse)
async def ingest_settlements(
    file: Optional[UploadFile] = File(None),
    settlements: Optional[List[dict]] = None,
    db: Session = Depends(get_db)
):
    """
    Ingest settlement records via CSV file upload or JSON payload.
    """
    records = []
    if file:
        try:
            content = await file.read()
            df = pd.read_csv(io.BytesIO(content))
            records = df.to_dict(orient="records")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to parse CSV file: {e}")
    elif settlements is not None:
        records = settlements
    else:
        raise HTTPException(status_code=400, detail="Provide either a CSV file or JSON list of settlements.")

    processed = 0
    inserted = 0
    errors = []
    
    required_cols = {"settlement_id", "transaction_reference", "gross_amount", "net_amount", "settlement_date"}
    
    for idx, row in enumerate(records):
        missing = required_cols - set(row.keys())
        if missing:
            errors.append({"row": idx, "error": f"Missing columns: {missing}"})
            continue
            
        sett_id = str(row["settlement_id"]).strip()
        
        existing = db.query(Settlement).filter(Settlement.settlement_id == sett_id).first()
        if existing:
            processed += 1
            continue
            
        try:
            orig_ref = row["transaction_reference"]
            
            sett = Settlement(
                settlement_id=sett_id,
                transaction_reference=str(orig_ref).strip(),
                gross_amount=NormalizationService.normalize_amount(row["gross_amount"]),
                fee=NormalizationService.normalize_amount(row.get("fee", 0.0)),
                adjustment=NormalizationService.normalize_amount(row.get("adjustment", 0.0)),
                net_amount=NormalizationService.normalize_amount(row["net_amount"]),
                settlement_date=NormalizationService.normalize_date(row["settlement_date"]),
                status="PENDING",
                original_reference=str(orig_ref)
            )
            
            if not sett.settlement_date:
                errors.append({"row": idx, "error": f"Invalid settlement_date: {row['settlement_date']}"})
                continue
                
            db.add(sett)
            inserted += 1
        except Exception as e:
            errors.append({"row": idx, "error": f"Error inserting record: {e}"})
            
        processed += 1
        
    db.commit()
    
    if inserted > 0:
        AuditService.log_event(
            db,
            entity_type="settlements",
            entity_id="bulk_ingest",
            action="INGEST_SETTLEMENTS",
            actor="system",
            details={"inserted": inserted, "errors_count": len(errors)}
        )
        
    return IngestionResponse(processed_count=processed, inserted_count=inserted, errors=errors)
