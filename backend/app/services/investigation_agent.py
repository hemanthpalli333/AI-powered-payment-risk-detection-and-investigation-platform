import json
import os
from typing import Dict, Any, List
from sqlalchemy.orm import Session

try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

from backend.app.config.config import settings
from backend.app.database.models import ExceptionRecord, Investigation, AuditLog

class InvestigationAgent:
    @staticmethod
    def get_deterministic_analysis(exc_type: str, diff_amt: float, evidence: Dict[str, Any]) -> Dict[str, Any]:
        """
        Fallback analysis that executes deterministic logic based on exception type.
        Ensures the system functions even if the LLM API is unavailable.
        """
        evidence_list = []
        possible_causes = []
        rec_action = "MANUAL_REVIEW"
        summary = ""
        
        if exc_type == "AMOUNT_MISMATCH":
            pay_amt = evidence.get("payment_amount", 0.0)
            inv_amt = evidence.get("invoice_amount", 0.0)
            summary = f"Payment amount ({pay_amt}) and invoice amount ({inv_amt}) differ by {diff_amt}."
            evidence_list = [
                f"Payment amount registered in ledger: {pay_amt}",
                f"Invoice amount registered: {inv_amt}",
                f"Discrepancy: {diff_amt}"
            ]
            possible_causes = [
                "Processing fee or gateway fee deducted before settlement",
                "Partial payment by the customer",
                "Incorrect pricing or discount application in the invoice details"
            ]
            rec_action = "MANUAL_REVIEW"
            
        elif exc_type == "MISSING_INVOICE":
            summary = "A payment transaction occurred, but no invoice matches the payment references."
            evidence_list = [
                f"Payment Reference: {evidence.get('payment', {}).get('reference', 'N/A')}",
                f"Amount: {evidence.get('payment', {}).get('amount', 0.0)}"
            ]
            possible_causes = [
                "Payment was made without creating an invoice in the system",
                "Reference number entered by customer during payment contains typos",
                "Invoice exists in an external CRM but has not been synced to the database"
            ]
            rec_action = "MANUAL_REVIEW"
            
        elif exc_type == "MISSING_PAYMENT":
            summary = "An invoice is overdue/open, but no matching payment has been registered in the database."
            evidence_list = [
                f"Invoice Reference: {evidence.get('invoice', {}).get('reference', 'N/A')}",
                f"Invoice Amount: {evidence.get('invoice', {}).get('amount', 0.0)}"
            ]
            possible_causes = [
                "Customer has not paid the invoice",
                "Payment received via bank transfer but reference was omitted",
                "Ingestion delay of the payment gateway data feed"
            ]
            rec_action = "MANUAL_REVIEW"
            
        elif exc_type == "DUPLICATE_PAYMENT":
            summary = "Multiple payments with the same amount and reference were ingested, potentially indicating a double charge or duplicate upload."
            evidence_list = [
                f"Invoice ID: {evidence.get('invoice_id')}",
                f"Duplicate Transaction IDs: {', '.join(evidence.get('duplicate_transaction_ids', []))}"
            ]
            possible_causes = [
                "User clicked the payment button twice, creating dual card authorizations",
                "File ingestion task executed twice for the same settlement report",
                "Customer paid twice by mistake"
            ]
            rec_action = "MANUAL_REVIEW"
            
        elif exc_type == "REFERENCE_MISMATCH":
            summary = f"Fuzzy matching linked records based on amounts and dates, but references do not match exactly: '{evidence.get('payment_reference')}' vs '{evidence.get('invoice_reference')}'."
            evidence_list = [
                f"Payment Reference: {evidence.get('payment_reference')}",
                f"Invoice Reference: {evidence.get('invoice_reference')}"
            ]
            possible_causes = [
                "Customer made a typographical error when entering the reference ID",
                "Internal system generated a payment reference different from invoice reference ID"
            ]
            rec_action = "MANUAL_REVIEW"
            
        elif exc_type == "DATE_MISMATCH":
            summary = f"Payment date and bank transaction date differ by {evidence.get('date_difference_days')} days, exceeding the allowed threshold."
            evidence_list = [
                f"Payment Date: {evidence.get('payment_date')}",
                f"Bank Transaction Date: {evidence.get('bank_transaction_date')}"
            ]
            possible_causes = [
                "Payment took several days to clear (e.g. over a weekend or holiday)",
                "Clearing house recorded a delayed credit statement"
            ]
            rec_action = "MANUAL_REVIEW"
            
        elif exc_type == "SETTLEMENT_DISCREPANCY":
            summary = f"Discrepancy detected in settlement calculation. Discrepancy amount: {diff_amt}."
            evidence_list = [
                f"Gross: {evidence.get('settlement_gross')}",
                f"Fee: {evidence.get('settlement_fee')}",
                f"Adjustment: {evidence.get('settlement_adjustment')}",
                f"Net Amount: {evidence.get('settlement_net')}",
                f"Expected Net (Gross - Fee - Adj): {evidence.get('expected_net')}"
            ]
            possible_causes = [
                "Incorrect processing fees charged by the merchant processor",
                "Gateway held a rolling reserve that was not reported in adjustments",
                "FX conversion discrepancy"
            ]
            rec_action = "MARK_EXCEPTION"
            
        else:
            summary = "Generic transaction mismatch requiring manual verification."
            evidence_list = ["No deterministic rules triggered."]
            possible_causes = ["Data input error", "System mapping misalignment"]
            rec_action = "MANUAL_REVIEW"
            
        return {
            "exception_summary": summary,
            "possible_causes": possible_causes,
            "recommended_action": rec_action,
            "confidence": 0.85,
            "evidence": evidence_list,
            "missing_information": []
        }

    @classmethod
    def investigate_exception(cls, db: Session, exception_id: int) -> Investigation:
        """
        Investigate an exception.
        If GEMINI_API_KEY is configured, call Gemini for AI reasoning.
        Otherwise, fallback to deterministic analysis.
        """
        exception = db.query(ExceptionRecord).filter(ExceptionRecord.id == exception_id).first()
        if not exception:
            raise ValueError(f"Exception ID {exception_id} not found.")

        # Load evidence
        evidence_dict = {}
        try:
            evidence_dict = json.loads(exception.evidence)
        except Exception:
            pass

        # Try AI Investigation if API Key is set and module is available
        api_key = settings.GEMINI_API_KEY or os.environ.get("GEMINI_API_KEY", "")
        ai_success = False
        analysis = {}

        if api_key and GEMINI_AVAILABLE:
            try:
                genai.configure(api_key=api_key)
                # Initialize model
                model = genai.GenerativeModel(settings.GEMINI_MODEL)
                
                # Format prompt
                prompt = f"""
                You are ReconAI Investigator, a high-precision AI finance-controller assistant.
                You are analyzing a financial reconciliation exception.
                
                Exception Type: {exception.exception_type}
                Difference Amount: {exception.difference_amount}
                Evidence Details:
                {json.dumps(evidence_dict, indent=2)}
                
                Analyze the discrepancy. Distinguish facts from hypotheses. 
                Do not claim a fee or adjustment occurred unless confirmed in the data.
                If details are vague, list them as possible causes, but recommend MANUAL_REVIEW.
                
                Return a structured JSON object matching this schema:
                {{
                  "exception_summary": "Plain text summary explaining the discrepancy.",
                  "possible_causes": ["Cause 1", "Cause 2"],
                  "recommended_action": "AUTO_RECONCILE" | "MANUAL_REVIEW" | "MARK_EXCEPTION" | "ESCALATE",
                  "confidence": 0.0 to 1.0 (float reflecting your analysis confidence),
                  "evidence": ["Fact 1", "Fact 2"],
                  "missing_information": ["Missing details (if any)"]
                }}
                
                Rely ONLY on JSON output. Do not wrap in markdown tags or add extra conversational text.
                """
                
                response = model.generate_content(
                    prompt,
                    generation_config={"response_mime_type": "application/json"}
                )
                
                # Parse JSON response
                resp_text = response.text.strip()
                # strip markdown code fence if model ignored configuration
                if resp_text.startswith("```"):
                    lines = resp_text.split("\n")
                    if lines[0].startswith("```json"):
                        resp_text = "\n".join(lines[1:-1])
                    elif lines[0].startswith("```"):
                        resp_text = "\n".join(lines[1:-1])
                
                analysis = json.loads(resp_text)
                ai_success = True
                print(f"AI investigation successful for Exception ID {exception_id}")
            except Exception as e:
                print(f"LLM investigation failed. Falling back to deterministic logic. Error: {e}")

        # Fallback to deterministic if AI was not run or failed
        if not ai_success:
            analysis = cls.get_deterministic_analysis(
                exception.exception_type, 
                exception.difference_amount, 
                evidence_dict
            )

        # Map analysis into database model
        investigation = Investigation(
            exception_id=exception.id,
            summary=analysis.get("exception_summary", "Unable to analyze discrepancy."),
            possible_causes=json.dumps(analysis.get("possible_causes", [])),
            recommendation=analysis.get("recommended_action", "MANUAL_REVIEW"),
            confidence=float(analysis.get("confidence", 0.70)),
        )
        
        # Update exception status
        exception.status = "INVESTIGATING"
        
        db.add(investigation)
        db.commit()
        db.refresh(investigation)

        # Audit log
        db.add(AuditLog(
            entity_type="investigation",
            entity_id=str(investigation.id),
            action="INVESTIGATE",
            actor="LLM_investigator" if ai_success else "deterministic_investigator",
            details=json.dumps({
                "exception_id": exception.id,
                "recommendation": investigation.recommendation,
                "confidence": investigation.confidence,
                "ai_success": ai_success
            })
        ))
        db.commit()
        
        return investigation
