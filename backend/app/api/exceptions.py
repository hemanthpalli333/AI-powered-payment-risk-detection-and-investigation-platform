import json
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from backend.app.database.database import get_db
from backend.app.database.models import ExceptionRecord
from backend.app.schemas.schemas import ExceptionResponse

router = APIRouter(prefix="/exceptions", tags=["Exceptions"])

@router.get("", response_model=List[ExceptionResponse])
def list_exceptions(
    status: Optional[str] = Query(None, description="Filter by status (PENDING, INVESTIGATING, RESOLVED, ESCALATED)"),
    exception_type: Optional[str] = Query(None, description="Filter by exception type"),
    min_amount: Optional[float] = Query(None, description="Filter by minimum difference amount"),
    db: Session = Depends(get_db)
):
    """
    Lists exceptions with optional filters.
    """
    query = db.query(ExceptionRecord)
    
    if status:
        query = query.filter(ExceptionRecord.status == status)
    if exception_type:
        query = query.filter(ExceptionRecord.exception_type == exception_type)
    if min_amount is not None:
        query = query.filter(ExceptionRecord.difference_amount >= min_amount)
        
    records = query.order_by(ExceptionRecord.created_at.desc()).all()
    
    # Parse evidence JSON strings in records to dicts for output serialization
    parsed_records = []
    for rec in records:
        evidence_dict = {}
        try:
            evidence_dict = json.loads(rec.evidence) if rec.evidence else {}
        except Exception:
            evidence_dict = {"raw": rec.evidence}
            
        parsed_records.append(
            ExceptionResponse(
                id=rec.id,
                transaction_id=rec.transaction_id,
                exception_type=rec.exception_type,
                difference_amount=rec.difference_amount,
                evidence=evidence_dict,
                status=rec.status,
                created_at=rec.created_at
            )
        )
        
    return parsed_records


@router.get("/{exception_id}", response_model=ExceptionResponse)
def get_exception(exception_id: int, db: Session = Depends(get_db)):
    """
    Retrieves detail of a specific exception by ID.
    """
    rec = db.query(ExceptionRecord).filter(ExceptionRecord.id == exception_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail=f"Exception ID {exception_id} not found.")
        
    evidence_dict = {}
    try:
        evidence_dict = json.loads(rec.evidence) if rec.evidence else {}
    except Exception:
        evidence_dict = {"raw": rec.evidence}
        
    return ExceptionResponse(
        id=rec.id,
        transaction_id=rec.transaction_id,
        exception_type=rec.exception_type,
        difference_amount=rec.difference_amount,
        evidence=evidence_dict,
        status=rec.status,
        created_at=rec.created_at
    )
