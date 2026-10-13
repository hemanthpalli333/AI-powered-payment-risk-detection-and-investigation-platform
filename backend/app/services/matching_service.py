import os
import joblib
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple, Optional
from rapidfuzz import fuzz

from backend.app.config.config import settings
from backend.app.services.normalization_service import NormalizationService

class MatchingService:
    def __init__(self):
        self.ml_model = None
        self.load_ml_model()
        
    def load_ml_model(self):
        """Try to load the trained ML matcher model."""
        if os.path.exists(settings.ML_MODEL_PATH):
            try:
                self.ml_model = joblib.load(settings.ML_MODEL_PATH)
                print(f"ML Model loaded successfully from {settings.ML_MODEL_PATH}")
            except Exception as e:
                print(f"Error loading ML model from {settings.ML_MODEL_PATH}: {e}")
                self.ml_model = None

    def calculate_exact_match(self, payment: Any, candidate: Any, cand_type: str) -> Optional[Dict[str, Any]]:
        """
        Level 1 --- Exact Matching
        Requires exact normalized references, exact amounts, and dates within 1 day.
        """
        # Normalize fields
        pay_ref = NormalizationService.normalize_reference(payment.payment_reference)
        pay_amt = payment.amount
        pay_date = payment.payment_date
        
        if cand_type == "bank_transaction":
            cand_ref = NormalizationService.normalize_reference(candidate.bank_reference)
            cand_amt = candidate.amount
            cand_date = candidate.transaction_date
        elif cand_type == "invoice":
            cand_ref = NormalizationService.normalize_reference(candidate.invoice_reference)
            cand_amt = candidate.invoice_amount
            cand_date = candidate.invoice_date
        elif cand_type == "settlement":
            cand_ref = NormalizationService.normalize_reference(candidate.transaction_reference)
            cand_amt = candidate.gross_amount
            cand_date = candidate.settlement_date
        else:
            return None
            
        # Amount match
        if abs(pay_amt - cand_amt) > 0.01:
            return None
            
        # Reference match
        if not pay_ref or pay_ref != cand_ref:
            return None
            
        # Date proximity (within 1 day)
        date_diff = abs((pay_date - cand_date).days) if pay_date and cand_date else 999
        if date_diff > 1:
            return None
            
        return {
            "match_method": "EXACT",
            "match_confidence": 100.0,
            "component_scores": {
                "amount": 40.0,
                "reference": 30.0,
                "date": 15.0,
                "customer": 15.0
            }
        }

    def calculate_rule_match(self, payment: Any, candidate: Any, cand_type: str) -> Dict[str, Any]:
        """
        Level 2 --- Rule-Based Matching
        Amount match = 40 points
        Reference match = 30 points
        Date similarity = 15 points
        Customer match = 15 points
        Total = 100 points
        """
        pay_ref = NormalizationService.normalize_reference(payment.payment_reference)
        pay_core = NormalizationService.extract_core_reference(payment.payment_reference)
        pay_amt = payment.amount
        pay_date = payment.payment_date
        pay_cust = payment.customer_id
        
        if cand_type == "bank_transaction":
            cand_ref = NormalizationService.normalize_reference(candidate.bank_reference)
            cand_core = NormalizationService.extract_core_reference(candidate.bank_reference)
            cand_amt = candidate.amount
            cand_date = candidate.transaction_date
            cand_cust = getattr(candidate, "customer_id", None)
            desc = (candidate.description or "").lower()
        elif cand_type == "invoice":
            cand_ref = NormalizationService.normalize_reference(candidate.invoice_reference)
            cand_core = NormalizationService.extract_core_reference(candidate.invoice_reference)
            cand_amt = candidate.invoice_amount
            cand_date = candidate.invoice_date
            cand_cust = candidate.customer_id
            desc = ""
        elif cand_type == "settlement":
            cand_ref = NormalizationService.normalize_reference(candidate.transaction_reference)
            cand_core = NormalizationService.extract_core_reference(candidate.transaction_reference)
            cand_amt = candidate.gross_amount
            cand_date = candidate.settlement_date
            cand_cust = None
            desc = ""
        else:
            return {"match_method": "RULE", "match_confidence": 0.0, "component_scores": {}}

        # 1. Amount match (40 pts)
        amt_diff = abs(pay_amt - cand_amt)
        if amt_diff <= 0.01:
            amt_score = 40.0
        elif amt_diff <= 10.0:
            amt_score = 30.0
        elif amt_diff <= 100.0:
            amt_score = 15.0
        else:
            amt_score = 0.0
            
        # 2. Reference match (30 pts)
        if pay_ref and pay_ref == cand_ref:
            ref_score = 30.0
        elif pay_core and pay_core == cand_core:
            ref_score = 25.0
        else:
            # Fuzzy match reference
            sim = fuzz.token_sort_ratio(pay_ref or "", cand_ref or "")
            if sim >= 80.0:
                ref_score = 20.0
            elif sim >= 60.0:
                ref_score = 10.0
            else:
                ref_score = 0.0
                
        # 3. Date similarity (15 pts)
        if pay_date and cand_date:
            if cand_type == "settlement":
                # Settlements normally lag by 1-7 days, do not penalize if within normal window
                delta_days = (cand_date - pay_date).days
                if 0 <= delta_days <= 7:
                    date_score = 15.0
                elif -2 <= delta_days < 0 or 7 < delta_days <= 14:
                    date_score = 10.0
                else:
                    date_score = 0.0
            else:
                date_diff = abs((pay_date - cand_date).days)
                if date_diff == 0:
                    date_score = 15.0
                elif date_diff <= 1:
                    date_score = 12.0
                elif date_diff <= 3:
                    date_score = 8.0
                elif date_diff <= 7:
                    date_score = 5.0
                else:
                    date_score = 0.0
        else:
            date_score = 0.0
            
        # 4. Customer match (15 pts)
        cust_score = 0.0
        if pay_cust:
            if cand_cust and pay_cust == cand_cust:
                cust_score = 15.0
            elif desc and pay_cust.lower() in desc:
                cust_score = 10.0
            elif desc and pay_ref and pay_ref in desc:
                cust_score = 10.0
                
        total_score = amt_score + ref_score + date_score + cust_score
        
        return {
            "match_method": "RULE",
            "match_confidence": float(total_score),
            "component_scores": {
                "amount": float(amt_score),
                "reference": float(ref_score),
                "date": float(date_score),
                "customer": float(cust_score)
            }
        }

    def calculate_fuzzy_match(self, payment: Any, candidate: Any, cand_type: str) -> Dict[str, Any]:
        """
        Level 3 --- Fuzzy Matching
        Combines fuzzy similarities of amount, references, dates, and descriptions.
        """
        pay_ref = payment.payment_reference or ""
        pay_amt = payment.amount
        pay_date = payment.payment_date
        pay_cust = payment.customer_id or ""
        
        if cand_type == "bank_transaction":
            cand_ref = candidate.bank_reference or ""
            cand_amt = candidate.amount
            cand_date = candidate.transaction_date
            cand_cust = getattr(candidate, "customer_id", "") or ""
            desc = candidate.description or ""
        elif cand_type == "invoice":
            cand_ref = candidate.invoice_reference or ""
            cand_amt = candidate.invoice_amount
            cand_date = candidate.invoice_date
            cand_cust = candidate.customer_id or ""
            desc = ""
        elif cand_type == "settlement":
            cand_ref = candidate.transaction_reference or ""
            cand_amt = candidate.gross_amount
            cand_date = candidate.settlement_date
            cand_cust = ""
            desc = ""
        else:
            return {"match_method": "FUZZY", "match_confidence": 0.0, "component_scores": {}}

        # Amount similarity (1.0 = exact, 0.0 = completely different)
        max_amt = max(pay_amt, cand_amt, 1.0)
        amount_sim = max(0.0, 1.0 - (abs(pay_amt - cand_amt) / max_amt))
        
        # Reference similarity using RapidFuzz
        ref_sim = fuzz.token_sort_ratio(pay_ref.lower(), cand_ref.lower()) / 100.0
        
        # Date similarity
        if pay_date and cand_date:
            if cand_type == "settlement":
                delta_days = (cand_date - pay_date).days
                if 0 <= delta_days <= 7:
                    date_sim = 1.0
                else:
                    abs_diff = min(abs(delta_days), 30)
                    date_sim = max(0.0, 1.0 - (abs_diff / 30.0))
            else:
                date_diff = abs((pay_date - cand_date).days)
                date_sim = max(0.0, 1.0 - (date_diff / 15.0)) # 15 days max span for similarity
        else:
            date_sim = 0.0
            
        # Customer similarity
        cust_sim = 1.0 if (pay_cust and cand_cust and pay_cust == cand_cust) else 0.0
        if cust_sim == 0.0 and pay_cust.lower() in desc.lower():
            cust_sim = 0.8
            
        # Description fuzzy match
        desc_sim = 0.0
        if desc:
            desc_sim = fuzz.partial_ratio(pay_ref.lower(), desc.lower()) / 100.0
            
        # Combined score (weighted average)
        # Weighting: Amount 40%, Reference 30%, Date 15%, Customer 15%
        weighted_score = (
            (amount_sim * 40.0) +
            (max(ref_sim, desc_sim) * 30.0) +
            (date_sim * 15.0) +
            (cust_sim * 15.0)
        )
        
        return {
            "match_method": "FUZZY",
            "match_confidence": float(weighted_score),
            "component_scores": {
                "amount": float(amount_sim * 40.0),
                "reference": float(max(ref_sim, desc_sim) * 30.0),
                "date": float(date_sim * 15.0),
                "customer": float(cust_sim * 15.0)
            }
        }

    def calculate_ml_match(self, payment: Any, candidate: Any, cand_type: str) -> Optional[Dict[str, Any]]:
        """
        Level 4 --- Machine Learning Matcher
        Predicts match probability using the saved model if loaded.
        """
        if not self.ml_model:
            return None
            
        # Generate features
        features = self.extract_ml_features(payment, candidate, cand_type)
        
        try:
            # Predict probability
            df_features = pd.DataFrame([features])
            prob = self.ml_model.predict_proba(df_features)[0][1] # Probability of class 1 (match)
            confidence = prob * 100.0
            
            return {
                "match_method": "ML",
                "match_confidence": float(confidence),
                "component_scores": {
                    "ml_probability": float(prob)
                }
            }
        except Exception as e:
            print(f"Error predicting ML match: {e}")
            return None

    def extract_ml_features(self, payment: Any, candidate: Any, cand_type: str) -> Dict[str, float]:
        """Helper to extract ML features for a pair of records."""
        pay_ref = payment.payment_reference or ""
        pay_amt = payment.amount
        pay_date = payment.payment_date
        pay_cust = payment.customer_id or ""
        
        if cand_type == "bank_transaction":
            cand_ref = candidate.bank_reference or ""
            cand_amt = candidate.amount
            cand_date = candidate.transaction_date
            cand_cust = getattr(candidate, "customer_id", "") or ""
            desc = candidate.description or ""
        elif cand_type == "invoice":
            cand_ref = candidate.invoice_reference or ""
            cand_amt = candidate.invoice_amount
            cand_date = candidate.invoice_date
            cand_cust = candidate.customer_id or ""
            desc = ""
        elif cand_type == "settlement":
            cand_ref = candidate.transaction_reference or ""
            cand_amt = candidate.gross_amount
            cand_date = candidate.settlement_date
            cand_cust = ""
            desc = ""
        else:
            return {}

        amt_diff = abs(pay_amt - cand_amt)
        max_amt = max(pay_amt, cand_amt, 1.0)
        amt_ratio = amt_diff / max_amt
        
        date_diff = abs((pay_date - cand_date).days) if pay_date and cand_date else 999
        
        ref_sim = fuzz.token_sort_ratio(pay_ref.lower(), cand_ref.lower()) / 100.0
        desc_sim = fuzz.partial_ratio(pay_ref.lower(), desc.lower()) / 100.0 if desc else 0.0
        
        cust_match = 1.0 if (pay_cust and cand_cust and pay_cust == cand_cust) else 0.0
        currency_match = 1.0 # assume same currency for now
        
        return {
            "amount_diff": float(amt_diff),
            "amount_ratio": float(amt_ratio),
            "date_diff": float(date_diff),
            "reference_similarity": float(max(ref_sim, desc_sim)),
            "customer_match": float(cust_match),
            "currency_match": float(currency_match)
        }

    def evaluate_pair(self, payment: Any, candidate: Any, cand_type: str) -> Dict[str, Any]:
        """
        Evaluate a single pair, selecting the best matching mechanism.
        We always check Level 1 (Exact) first. If it matches, we return it.
        Otherwise, we evaluate Level 2 (Rule) and Level 3 (Fuzzy).
        If ML model is available (Level 4), we also run it and choose the highest confidence score.
        """
        # Level 1
        exact_res = self.calculate_exact_match(payment, candidate, cand_type)
        if exact_res:
            return exact_res
            
        # Level 2 & 3
        rule_res = self.calculate_rule_match(payment, candidate, cand_type)
        fuzzy_res = self.calculate_fuzzy_match(payment, candidate, cand_type)
        
        best_res = rule_res if rule_res["match_confidence"] >= fuzzy_res["match_confidence"] else fuzzy_res
        
        # Level 4 (ML Matcher)
        if self.ml_model:
            ml_res = self.calculate_ml_match(payment, candidate, cand_type)
            if ml_res and ml_res["match_confidence"] > best_res["match_confidence"]:
                best_res = ml_res
                
        return best_res
