import pandas as pd
import numpy as np
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import Dict, Any

from backend.app.database.database import get_db
from backend.app.database.models import Payment, ReconciliationResult, ExceptionRecord
from backend.app.schemas.schemas import MonitoringReport, DataQualityReport

router = APIRouter(prefix="/monitoring", tags=["Monitoring"])

def calculate_drift_evidently(ref_df: pd.DataFrame, curr_df: pd.DataFrame) -> Dict[str, Any]:
    """
    Attempts to run Evidently report on amount distribution drift.
    Falls back gracefully if Evidently metrics fail to compile or import.
    """
    try:
        from evidently.report import Report
        from evidently.metric_preset import DataDriftPreset
        
        report = Report(metrics=[DataDriftPreset(num_features=["amount"])])
        report.run(reference_data=ref_df, current_data=curr_df)
        dict_report = report.as_dict()
        
        # Parse drift details from Evidently report
        metrics = dict_report.get("metrics", [])
        drift_detected = False
        drift_share = 0.0
        
        # Search for DatasetDriftMetric output in evidently results
        for m in metrics:
            if "DatasetDriftMetric" in str(m.get("metric")):
                result = m.get("result", {})
                drift_detected = bool(result.get("dataset_drift", False))
                drift_share = float(result.get("share_of_drifted_features", 0.0))
                break
                
        return {
            "success": True,
            "drift_detected": drift_detected,
            "drift_share": drift_share,
            "details": "Evidently report executed successfully."
        }
    except Exception as e:
        # Fallback to direct calculation if Evidently fails or is missing
        ref_mean = float(ref_df["amount"].mean()) if not ref_df.empty else 0.0
        curr_mean = float(curr_df["amount"].mean()) if not curr_df.empty else 0.0
        
        diff = abs(curr_mean - ref_mean)
        percent_diff = (diff / ref_mean) if ref_mean > 0 else 0.0
        drift_detected = bool(percent_diff > 0.25) # 25% change counts as drift
        
        return {
            "success": False,
            "drift_detected": drift_detected,
            "drift_share": 1.0 if drift_detected else 0.0,
            "details": f"Evidently execution bypassed (Fallback triggers). Ref Mean: {ref_mean:.2f}, Current Mean: {curr_mean:.2f}. Diff: {percent_diff*100:.1f}%"
        }

@router.get("", response_model=MonitoringReport)
def get_monitoring_report(db: Session = Depends(get_db)):
    """
    Retrieves data quality metrics, match performance, and Evidently drift status.
    """
    # 1. Gather all payments
    payments = db.query(Payment).all()
    total_payments = len(payments)
    
    missing_fields = 0
    duplicate_records = 0
    invalid_amounts = 0
    invalid_dates = 0
    currency_inconsistencies = 0
    
    seen_ids = set()
    for p in payments:
        # Check missing fields
        if not p.payment_reference or not p.customer_id:
            missing_fields += 1
        # Check duplicates
        if p.transaction_id in seen_ids:
            duplicate_records += 1
        seen_ids.add(p.transaction_id)
        # Check invalid amounts
        if p.amount is None or p.amount <= 0.0:
            invalid_amounts += 1
        # Check invalid dates
        if not p.payment_date:
            invalid_dates += 1
        # Check currency inconsistencies (standard currency is INR)
        if p.currency != "INR":
            currency_inconsistencies += 1
            
    dq = DataQualityReport(
        total_records=total_payments,
        missing_fields=missing_fields,
        duplicate_records=duplicate_records,
        invalid_amounts=invalid_amounts,
        invalid_dates=invalid_dates,
        currency_inconsistencies=currency_inconsistencies
    )
    
    # 2. Performance rates
    reconciled = db.query(Payment).filter(Payment.status == "RECONCILED").count()
    exceptions = db.query(Payment).filter(Payment.status == "EXCEPTION").count()
    unmatched = db.query(Payment).filter(Payment.status == "UNMATCHED").count()
    
    match_rate = (reconciled / total_payments * 100.0) if total_payments > 0 else 0.0
    auto_match_rate = match_rate
    manual_review_rate = (exceptions / total_payments * 100.0) if total_payments > 0 else 0.0
    unmatched_rate = (unmatched / total_payments * 100.0) if total_payments > 0 else 0.0
    exception_rate = manual_review_rate
    
    # 3. Drift Analysis
    # Let's create reference and current dataframes
    drift_status = "HEALTHY"
    drift_details = {}
    
    if total_payments >= 5:
        # Build pandas dataframes
        data = [{"amount": p.amount, "date": p.payment_date} for p in payments]
        df_curr = pd.DataFrame(data)
        
        # Build a synthetic baseline representing typical transactions (mean INR 6000)
        np.random.seed(42)
        ref_amounts = np.random.normal(loc=6000.0, scale=1500.0, size=100)
        df_ref = pd.DataFrame({"amount": ref_amounts})
        
        drift_res = calculate_drift_evidently(df_ref, df_curr)
        drift_details = drift_res
        
        if drift_res["drift_detected"]:
            drift_status = "DRIFT_DETECTED"
        else:
            drift_status = "HEALTHY"
    else:
        drift_status = "REVIEW_REQUIRED"
        drift_details = {"details": "Insufficient records (minimum 5 required) to execute drift comparison."}
        
    return MonitoringReport(
        data_quality=dq,
        match_rate=round(match_rate, 2),
        auto_match_rate=round(auto_match_rate, 2),
        manual_review_rate=round(manual_review_rate, 2),
        unmatched_rate=round(unmatched_rate, 2),
        exception_rate=round(exception_rate, 2),
        drift_status=drift_status,
        drift_details=drift_details
    )
