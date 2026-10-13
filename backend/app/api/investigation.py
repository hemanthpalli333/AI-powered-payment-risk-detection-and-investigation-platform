import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.app.database.database import get_db
from backend.app.schemas.schemas import InvestigationResponse
from backend.app.services.investigation_agent import InvestigationAgent
from backend.app.database.models import Investigation

router = APIRouter(prefix="/investigation", tags=["Investigation"])

@router.post("/{exception_id}", response_model=InvestigationResponse)
def trigger_investigation(exception_id: int, db: Session = Depends(get_db)):
    """
    Triggers an AI investigation on the specified exception.
    Routs the case to either the Gemini LLM or the rule-based backup, returning analysis & recommendation.
    """
    try:
        investigation = InvestigationAgent.investigate_exception(db, exception_id)
        
        # Parse possible causes JSON string to list for the response model
        causes_list = []
        try:
            causes_list = json.loads(investigation.possible_causes) if investigation.possible_causes else []
        except Exception:
            causes_list = [investigation.possible_causes]
            
        return InvestigationResponse(
            id=investigation.id,
            exception_id=investigation.exception_id,
            summary=investigation.summary,
            possible_causes=causes_list,
            recommendation=investigation.recommendation,
            confidence=investigation.confidence,
            created_at=investigation.created_at
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI Investigation failed: {e}")
