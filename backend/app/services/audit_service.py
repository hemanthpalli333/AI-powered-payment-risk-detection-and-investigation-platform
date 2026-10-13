import json
import datetime
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from backend.app.database.models import AuditLog

class AuditService:
    @staticmethod
    def log_event(db: Session, entity_type: str, entity_id: str, action: str, actor: str, details: Dict[str, Any]) -> AuditLog:
        """
        Creates an immutable audit log record.
        """
        log = AuditLog(
            entity_type=entity_type,
            entity_id=str(entity_id),
            action=action,
            actor=actor,
            details=json.dumps(details),
            created_at=datetime.datetime.utcnow()
        )
        db.add(log)
        db.commit()
        db.refresh(log)
        return log

    @staticmethod
    def get_logs_for_entity(db: Session, entity_type: str, entity_id: str) -> List[AuditLog]:
        """
        Retrieves audit trail for a specific record.
        """
        return db.query(AuditLog).filter(
            AuditLog.entity_type == entity_type,
            AuditLog.entity_id == str(entity_id)
        ).order_by(AuditLog.created_at.desc()).all()

    @staticmethod
    def get_logs_by_transaction(db: Session, transaction_id: str) -> List[AuditLog]:
        """
        Retrieves logs relating to a transaction_id (checking inside JSON details if necessary or by entity_id).
        """
        # Look for entity_id matching the transaction_id or details matching it
        return db.query(AuditLog).filter(
            (AuditLog.entity_id == transaction_id) | 
            (AuditLog.details.like(f"%{transaction_id}%"))
        ).order_by(AuditLog.created_at.desc()).all()
