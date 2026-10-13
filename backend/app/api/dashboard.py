from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Dict, Any, List
import datetime

from backend.app.database.database import get_db
from backend.app.database.models import Payment, BankTransaction, Invoice, Settlement, ExceptionRecord, ReconciliationResult

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

@router.get("/metrics")
def get_dashboard_metrics(db: Session = Depends(get_db)):
    """
    Returns aggregated KPI metrics and chart datasets for the dashboard.
    """
    # 1. Total Counts
    total_payments = db.query(Payment).count()
    total_bank = db.query(BankTransaction).count()
    total_invoices = db.query(Invoice).count()
    total_settlements = db.query(Settlement).count()
    
    # 2. Payment Status Distribution
    status_counts = db.query(Payment.status, func.count(Payment.id)).group_by(Payment.status).all()
    status_dist = {status: count for status, count in status_counts}
    
    reconciled = status_dist.get("RECONCILED", 0)
    exceptions = status_dist.get("EXCEPTION", 0)
    pending = status_dist.get("PENDING", 0)
    unmatched = status_dist.get("UNMATCHED", 0)
    
    reconciliation_rate = (reconciled / total_payments * 100.0) if total_payments > 0 else 0.0
    
    # 3. Exception Type Distribution
    exc_type_counts = db.query(
        ExceptionRecord.exception_type, 
        func.count(ExceptionRecord.id),
        func.sum(ExceptionRecord.difference_amount)
    ).filter(ExceptionRecord.status.in_(["PENDING", "INVESTIGATING"])).group_by(ExceptionRecord.exception_type).all()
    
    exception_breakdown = []
    total_exception_value = 0.0
    
    for exc_type, count, diff_sum in exc_type_counts:
        val = diff_sum or 0.0
        total_exception_value += val
        exception_breakdown.append({
            "type": exc_type,
            "count": count,
            "value": round(val, 2)
        })
        
    # 4. Daily Reconciliation Trend (Last 7 days)
    # Group payments reconciled by date
    today = datetime.datetime.utcnow().date()
    seven_days_ago = today - datetime.timedelta(days=7)
    
    trend_res = db.query(
        func.date(ReconciliationResult.created_at).label("date"),
        func.count(ReconciliationResult.id).label("count")
    ).filter(
        ReconciliationResult.created_at >= seven_days_ago
    ).group_by(
        func.date(ReconciliationResult.created_at)
    ).order_by("date").all()
    
    daily_trend = [{"date": str(t.date), "reconciled_count": t.count} for t in trend_res]
    
    # Default trend filling if empty
    if not daily_trend:
        for i in range(7):
            d = today - datetime.timedelta(days=i)
            daily_trend.append({"date": str(d), "reconciled_count": 0})
        daily_trend.reverse()

    return {
        "kpis": {
            "total_records": total_payments + total_bank + total_invoices + total_settlements,
            "total_payments": total_payments,
            "reconciled": reconciled,
            "pending": pending,
            "unmatched": unmatched,
            "exceptions": exceptions,
            "exception_value": round(total_exception_value, 2),
            "reconciliation_rate": round(reconciliation_rate, 2),
            "auto_match_rate": round(reconciliation_rate, 2) # simplified
        },
        "status_distribution": {
            "reconciled": reconciled,
            "exceptions": exceptions,
            "pending": pending,
            "unmatched": unmatched
        },
        "exception_breakdown": exception_breakdown,
        "daily_trend": daily_trend
    }
