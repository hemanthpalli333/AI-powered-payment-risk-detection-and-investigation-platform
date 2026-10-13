import re
from datetime import datetime
from typing import Any, Union, Optional

class NormalizationService:
    @staticmethod
    def normalize_amount(amount_val: Any) -> float:
        """
        Normalize amounts into floats.
        Handles values like '₹12,450', '12450.00', '12,450 INR', '$100.50'
        """
        if amount_val is None:
            return 0.0
        if isinstance(amount_val, (int, float)):
            return float(amount_val)
        
        # Convert to string and clean
        val_str = str(amount_val).strip()
        # Remove currency symbols and other characters except digits, dots, and minus signs
        # Keep commas to remove them later
        cleaned = re.sub(r"[^\d.,\-]", "", val_str)
        
        # Handle commas (e.g., 12,450.00 -> 12450.00 or European format 12.450,00 -> 12450.00)
        if "," in cleaned and "." in cleaned:
            # Determine which is the decimal separator
            comma_idx = cleaned.rfind(",")
            dot_idx = cleaned.rfind(".")
            if comma_idx > dot_idx:
                # European format: 12.450,00 -> remove dot, replace comma with dot
                cleaned = cleaned.replace(".", "").replace(",", ".")
            else:
                # Standard format: 12,450.00 -> remove comma
                cleaned = cleaned.replace(",", "")
        elif "," in cleaned:
            # Check if comma is decimal separator (e.g. "12450,50") or thousand separator ("12,450")
            # If comma is followed by exactly 2 or 1 digits at the end, it might be decimal
            parts = cleaned.split(",")
            if len(parts[-1]) <= 2:
                cleaned = ".".join(parts)
            else:
                cleaned = cleaned.replace(",", "")
                
        try:
            return float(cleaned)
        except ValueError:
            return 0.0

    @staticmethod
    def normalize_date(date_val: Any) -> Optional[datetime]:
        """
        Normalize dates into datetime objects.
        Handles standard formats, timestamp strings, etc.
        """
        if date_val is None:
            return None
        if isinstance(date_val, datetime):
            return date_val
        
        date_str = str(date_val).strip()
        
        # Try common formats
        formats = [
            "%Y-%m-%d",
            "%Y-%m-%d %H:%M:%S",
            "%d-%m-%Y",
            "%m/%d/%Y",
            "%d/%m/%Y",
            "%Y/%m/%d",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S.%fZ"
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
                
        # Try parsing date-only from timestamp string
        if len(date_str) > 10:
            try:
                return datetime.strptime(date_str[:10], "%Y-%m-%d")
            except ValueError:
                pass
                
        return None

    @staticmethod
    def normalize_reference(ref_val: Any) -> str:
        """
        Normalize reference codes to a standard lowercase alphanumeric string.
        Strips leading zeros in numeric parts to match:
        'PAY-0008921' -> 'pay8921'
        'pay-8921' -> 'pay8921'
        'PAY8921' -> 'pay8921'
        """
        if ref_val is None:
            return ""
        
        ref_str = str(ref_val).strip().lower()
        # Remove all non-alphanumeric characters
        alphanumeric = re.sub(r"[^a-z0-9]", "", ref_str)
        
        # Extract letters and numbers to strip leading zeros from the number
        match = re.match(r"^([a-z]+)?(0+)?([0-9]+)$", alphanumeric)
        if match:
            prefix = match.group(1) or ""
            number = match.group(3) or ""
            return prefix + number
            
        return alphanumeric

    @staticmethod
    def extract_core_reference(ref_val: Any) -> str:
        """
        Extract only the numeric core from a reference if possible.
        E.g., 'PAY-8921' -> '8921', 'BANK-8921' -> '8921'
        Allows rule/fuzzy matches between systems with prefix changes.
        """
        if ref_val is None:
            return ""
        
        ref_str = str(ref_val).strip().lower()
        # Find all digits in the string
        digits = re.findall(r"\d+", ref_str)
        if digits:
            # Return digits joined, stripping leading zeros of the first group
            return "".join(digits).lstrip("0")
        return ref_str
