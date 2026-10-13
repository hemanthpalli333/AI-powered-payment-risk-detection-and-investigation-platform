import json
import re
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
from typing import Dict, Any, List, Tuple

from backend.app.database.database import get_db
from backend.app.database.models import ExceptionRecord, Payment, ReconciliationResult, AuditLog
from backend.app.schemas.schemas import CopilotQueryRequest, CopilotResponse
from backend.app.services.audit_service import AuditService
from backend.app.config.config import settings

router = APIRouter(prefix="/copilot", tags=["Copilot"])

def run_db_query_for_copilot(query_text: str, db: Session) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Translates keywords in the natural language query into real database queries.
    Returns a description of what was queried, and the raw dataset.
    """
    query_lower = query_text.lower()
    results = []
    category = "general"
    
    # 1. "above [number]" parser
    threshold_amt = 0.0
    amt_match = re.search(r'(?:above|greater than|over|rs\.?|₹)\s*([\d,]+)', query_lower)
    if amt_match:
        try:
            threshold_amt = float(amt_match.group(1).replace(",", ""))
        except ValueError:
            pass
            
    # 2. Case: Duplicate payments
    if "duplicate" in query_lower:
        category = "duplicate_payments"
        dups = db.query(ExceptionRecord).filter(
            ExceptionRecord.exception_type == "DUPLICATE_PAYMENT",
            ExceptionRecord.status.in_(["PENDING", "INVESTIGATING"])
        ).all()
        for d in dups:
            results.append({
                "id": d.id,
                "transaction_id": d.transaction_id,
                "type": d.exception_type,
                "amount": d.difference_amount,
                "status": d.status
            })
            
    # 3. Case: Unresolved exceptions / value unresolved
    elif "unresolved" in query_lower or "how much" in query_lower or "outstanding" in query_lower:
        category = "unresolved_exceptions"
        q = db.query(ExceptionRecord).filter(ExceptionRecord.status.in_(["PENDING", "INVESTIGATING"]))
        if threshold_amt > 0:
            q = q.filter(ExceptionRecord.difference_amount >= threshold_amt)
            
        excs = q.all()
        for e in excs:
            results.append({
                "id": e.id,
                "transaction_id": e.transaction_id,
                "type": e.exception_type,
                "amount": e.difference_amount,
                "status": e.status
            })
            
    # 4. Case: Reconciliation rate / performance
    elif "rate" in query_lower or "percentage" in query_lower or "reconciled" in query_lower:
        category = "reconciliation_rate"
        total = db.query(Payment).count()
        reconciled = db.query(Payment).filter(Payment.status == "RECONCILED").count()
        rate = (reconciled / total * 100.0) if total > 0 else 0.0
        results = [{
            "total_payments": total,
            "reconciled_payments": reconciled,
            "reconciliation_rate_percent": round(rate, 2)
        }]
        
    # 5. Case: Common cause of exceptions
    elif "cause" in query_lower or "common" in query_lower or "why" in query_lower:
        category = "common_exceptions"
        counts = db.query(
            ExceptionRecord.exception_type,
            func.count(ExceptionRecord.id)
        ).group_by(ExceptionRecord.exception_type).all()
        for exc_type, cnt in counts:
            results.append({
                "exception_type": exc_type,
                "count": cnt
            })
            
    # Default: List all open exceptions
    else:
        category = "all_exceptions"
        excs = db.query(ExceptionRecord).limit(10).all()
        for e in excs:
            results.append({
                "id": e.id,
                "transaction_id": e.transaction_id,
                "type": e.exception_type,
                "amount": e.difference_amount,
                "status": e.status
            })
            
    return category, results


@router.post("/query", response_model=CopilotResponse)
def query_copilot(payload: CopilotQueryRequest, db: Session = Depends(get_db)):
    """
    Handles natural language queries from the finance user.
    Uses real database queries combined with the LLM or structured templates to return a verified response.
    """
    query_text = payload.query
    
    # 1. Fetch real ground-truth data from DB
    category, query_data = run_db_query_for_copilot(query_text, db)
    
    # 2. Try to generate answer using Gemini
    api_key = settings.GEMINI_API_KEY
    ai_success = False
    answer = ""
    
    if api_key and GEMINI_AVAILABLE:
        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(settings.GEMINI_MODEL)
            
            prompt = f"""
            You are ReconAI Copilot, a helpful AI assistant for a financial operations team.
            A user asked you: "{query_text}"
            
            Here is the verified data retrieved from the database to answer their question:
            {json.dumps(query_data, indent=2)}
            
            Write a clear, concise, and professional response summarizing this information.
            Do not fabricate any figures. Rely ONLY on the provided JSON data.
            If the data is empty, state clearly that no records match their request.
            """
            
            response = model.generate_content(prompt)
            answer = response.text.strip()
            ai_success = True
        except Exception as e:
            print(f"Copilot LLM query failed. Falling back to templates. Error: {e}")

    # 3. Fallback templates
    if not ai_success:
        if category == "duplicate_payments":
            if not query_data:
                answer = "No unresolved duplicate payments found in the system."
            else:
                answer = f"I found {len(query_data)} duplicate payment exceptions. The transaction IDs are: {', '.join([d['transaction_id'] for d in query_data])}."
                
        elif category == "unresolved_exceptions":
            if not query_data:
                answer = "There are no unresolved exceptions currently pending review."
            else:
                total_val = sum(d["amount"] for d in query_data)
                answer = f"There are {len(query_data)} unresolved exceptions pending review, totaling ₹{total_val:,.2f}. Exception types include: {', '.join(set([d['type'] for d in query_data]))}."
                
        elif category == "reconciliation_rate":
            stats = query_data[0]
            answer = f"The current reconciliation rate is {stats['reconciliation_rate_percent']}%. Out of {stats['total_payments']} total payments, {stats['reconciled_payments']} have been reconciled successfully."
            
        elif category == "common_exceptions":
            if not query_data:
                answer = "No exceptions have been logged in the system."
            else:
                summary_lines = [f"- {item['exception_type']}: {item['count']} occurrences" for item in query_data]
                answer = "Here is the count of exception types logged in the system:\n" + "\n".join(summary_lines)
                
        else:
            if not query_data:
                answer = "No exceptions found in the system."
            else:
                answer = f"Here are the recent exceptions in the system: " + ", ".join([f"{d['type']} ({d['transaction_id']})" for d in query_data])

    # Log copilot query in audit log
    AuditService.log_event(
        db,
        entity_type="copilot",
        entity_id="query",
        action="QUERY_COPILOT",
        actor="user",
        details={"query": query_text, "category": category, "ai_success": ai_success}
    )

    return CopilotResponse(answer=answer, query_results=query_data)
