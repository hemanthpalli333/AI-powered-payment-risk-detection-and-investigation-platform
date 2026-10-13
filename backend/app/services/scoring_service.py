from backend.app.config.config import settings

class ScoringService:
    @staticmethod
    def get_match_status(score: float, auto_match_thresh: float = None, high_conf_thresh: float = None, review_thresh: float = None) -> str:
        """
        Classifies match confidence score into categories:
        AUTO_MATCH (98-100), HIGH_CONFIDENCE (85-97), REVIEW (60-84), UNMATCHED (0-59)
        """
        auto_t = auto_match_thresh if auto_match_thresh is not None else settings.AUTO_MATCH_THRESHOLD
        high_t = high_conf_thresh if high_conf_thresh is not None else settings.HIGH_CONFIDENCE_THRESHOLD
        rev_t = review_thresh if review_thresh is not None else settings.REVIEW_THRESHOLD
        
        if score >= auto_t:
            return "AUTO_MATCH"
        elif score >= high_t:
            return "HIGH_CONFIDENCE"
        elif score >= rev_t:
            return "REVIEW"
        else:
            return "UNMATCHED"
            
    @staticmethod
    def get_reconciliation_status(score: float) -> str:
        """
        Helper to return the transaction status mapping.
        """
        status = ScoringService.get_match_status(score)
        if status == "AUTO_MATCH":
            return "RECONCILED"
        elif status in ("HIGH_CONFIDENCE", "REVIEW"):
            return "EXCEPTION"  # Needs AI investigation or human review
        else:
            return "UNMATCHED"
