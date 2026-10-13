import os
import sys
import pandas as pd
import numpy as np
from datetime import datetime
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, average_precision_score
import joblib
from rapidfuzz import fuzz

# Add project root to sys.path so we can import normalization service
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from backend.app.services.normalization_service import NormalizationService

def prepare_ml_dataset():
    # Paths to data
    pay_path = "sample_data/payments.csv"
    bank_path = "sample_data/bank_transactions.csv"
    
    if not os.path.exists(pay_path) or not os.path.exists(bank_path):
        print("Sample data not found. Please run the sample data generator first.")
        # Attempt to run it directly
        from sample_data.generate_sample_data import generate_data
        generate_data()
        
    df_pay = pd.read_csv(pay_path)
    df_bank = pd.read_csv(bank_path)
    
    # Clean/normalize values for pairing
    df_pay["clean_amount"] = df_pay["amount"].apply(NormalizationService.normalize_amount)
    df_pay["clean_date"] = df_pay["payment_date"].apply(NormalizationService.normalize_date)
    df_pay["clean_ref"] = df_pay["payment_reference"].apply(NormalizationService.normalize_reference)
    
    df_bank["clean_amount"] = df_bank["amount"].apply(NormalizationService.normalize_amount)
    df_bank["clean_date"] = df_bank["transaction_date"].apply(NormalizationService.normalize_date)
    df_bank["clean_ref"] = df_bank["bank_reference"].apply(NormalizationService.normalize_reference)
    
    # 1. SPLIT HOLD OUT TEST SET FIRST TO PREVENT LEAKAGE
    # We split based on payment transaction IDs
    train_pay, test_pay = train_test_split(df_pay, test_size=0.25, random_state=42)
    
    def generate_pairs(payment_df):
        features = []
        labels = []
        
        # 1. Positive Pairs
        for idx, pay in payment_df.iterrows():
            pay_id_num = pay["transaction_id"].replace("TXN", "").replace("A", "").replace("B", "")
            for b_idx, bank in df_bank.iterrows():
                bank_id_num = bank["bank_transaction_id"].replace("BTXN", "").replace("A", "").replace("B", "")
                
                if pay_id_num == bank_id_num:
                    feat = extract_features(pay, bank)
                    features.append(feat)
                    labels.append(1)
                    
        # 2. Negative Pairs
        for idx, pay in payment_df.iterrows():
            pay_id_num = pay["transaction_id"].replace("TXN", "").replace("A", "").replace("B", "")
            neg_count = 0
            for b_idx, bank in df_bank.iterrows():
                bank_id_num = bank["bank_transaction_id"].replace("BTXN", "").replace("A", "").replace("B", "")
                
                if pay_id_num != bank_id_num:
                    feat = extract_features(pay, bank)
                    
                    # Synthetic noise injection: add some noise to negative pairs 
                    # to make the model learn harder boundaries
                    if np.random.random() > 0.5:
                        feat["amount_diff"] += float(np.random.randint(-100, 100))
                        
                    features.append(feat)
                    labels.append(0)
                    neg_count += 1
                    if neg_count >= 3: 
                        break
                        
        return pd.DataFrame(features), np.array(labels)
        
    X_train, y_train = generate_pairs(train_pay)
    X_test, y_test = generate_pairs(test_pay)
    
    return X_train, X_test, y_train, y_test

def extract_features(pay, bank) -> dict:
    pay_amt = pay["clean_amount"]
    bank_amt = bank["clean_amount"]
    
    amt_diff = abs(pay_amt - bank_amt)
    max_amt = max(pay_amt, bank_amt, 1.0)
    amt_ratio = amt_diff / max_amt
    
    pay_date = pay["clean_date"]
    bank_date = bank["clean_date"]
    
    if pay_date and bank_date:
        date_diff = abs((pay_date - bank_date).days)
    else:
        date_diff = 999.0
        
    pay_ref = pay["clean_ref"] or ""
    bank_ref = bank["clean_ref"] or ""
    ref_sim = fuzz.token_sort_ratio(pay_ref, bank_ref) / 100.0
    
    # Try description fuzzy match
    desc = str(bank.get("description", "")).lower()
    desc_sim = fuzz.partial_ratio(pay_ref, desc) / 100.0 if desc else 0.0
    
    pay_cust = str(pay.get("customer_id", ""))
    bank_cust = str(bank.get("customer_id", ""))
    cust_match = 1.0 if (pay_cust and bank_cust and pay_cust == bank_cust) else 0.0
    
    currency_match = 1.0 if pay.get("currency") == bank.get("currency") else 0.0
    
    return {
        "amount_diff": float(amt_diff),
        "amount_ratio": float(amt_ratio),
        "date_diff": float(date_diff),
        "reference_similarity": float(max(ref_sim, desc_sim)),
        "customer_match": float(cust_match),
        "currency_match": float(currency_match)
    }

def train_model():
    print("Preparing dataset...")
    X_train, X_test, y_train, y_test = prepare_ml_dataset()
    
    print(f"Dataset generated. Train Positive ratio: {y_train.mean():.2f}")
    
    print("Training RandomForest model...")
    model = RandomForestClassifier(n_estimators=100, random_state=42)
    model.fit(X_train, y_train)
    
    # Evaluate
    preds = model.predict(X_test)
    probs = model.predict_proba(X_test)[:, 1]
    
    print("\n--- Model Evaluation Results ---")
    print(classification_report(y_test, preds))
    ap = average_precision_score(y_test, probs)
    print(f"Average Precision Score (PR-AUC): {ap:.4f}")
    
    # Save model artifact
    os.makedirs("ml/artifacts", exist_ok=True)
    model_path = "ml/artifacts/matcher_model.joblib"
    joblib.dump(model, model_path)
    print(f"\nModel artifact successfully saved to {model_path}")
    
    # Save features description for verification
    features_list = list(X_train.columns)
    print(f"Trained features order: {features_list}")

if __name__ == "__main__":
    train_model()
