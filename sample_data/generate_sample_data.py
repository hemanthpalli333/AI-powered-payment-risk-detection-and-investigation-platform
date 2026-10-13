import os
import pandas as pd
from datetime import datetime, timedelta

def generate_data():
    os.makedirs("sample_data", exist_ok=True)
    
    # Base date
    base_date = datetime(2026, 8, 20)
    
    # 1. Successful matches (TXN1001 to TXN1020)
    # Payment, Bank, Invoice, Settlement all match.
    payments = []
    bank_txns = []
    invoices = []
    settlements = []
    
    for i in range(1, 21):
        txn_id = f"TXN{1000+i}"
        cust_id = f"CUST{1000 + (i % 5)}"
        ref = f"REF-{1000+i}"
        amount = 5000.0 + (i * 100.0)
        date_val = base_date + timedelta(days=i%3)
        
        # Payment
        payments.append({
            "transaction_id": txn_id,
            "customer_id": cust_id,
            "payment_reference": ref,
            "amount": f"INR {amount:,.2f}", # non-normalized string
            "currency": "INR",
            "payment_date": date_val.strftime("%Y-%m-%d"),
            "payment_method": "UPI",
            "status": "PENDING"
        })
        
        # Bank
        bank_txns.append({
            "bank_transaction_id": f"BTXN{1000+i}",
            "bank_reference": f"BANK-{1000+i}", # Slightly different reference format
            "amount": amount,
            "transaction_date": (date_val + timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S"),
            "description": f"UPI PAY OUT TO {ref} CUSTOMER {cust_id}",
            "credit_debit": "CREDIT",
            "bank_name": "HDFC Bank"
        })
        
        # Invoice
        invoices.append({
            "invoice_id": f"INV-{1000+i}",
            "customer_id": cust_id,
            "invoice_reference": ref,
            "invoice_amount": amount,
            "invoice_date": (date_val - timedelta(days=1)).strftime("%Y-%m-%d"),
            "due_date": (date_val + timedelta(days=15)).strftime("%Y-%m-%d"),
            "currency": "INR",
            "status": "PENDING"
        })
        
        # Settlement
        fee = amount * 0.02
        net = amount - fee
        settlements.append({
            "settlement_id": f"SET-{1000+i}",
            "transaction_reference": ref,
            "gross_amount": amount,
            "fee": fee,
            "adjustment": 0.0,
            "net_amount": net,
            "settlement_date": (date_val + timedelta(days=3)).strftime("%Y-%m-%d"),
            "status": "PENDING"
        })

    # 2. Case: Amount Mismatch (TXN1021)
    # Payment = 12450, Bank = 12450, Invoice = 12000
    payments.append({
        "transaction_id": "TXN1021",
        "customer_id": "CUST2001",
        "payment_reference": "PAY-8921",
        "amount": "12,450.00",
        "currency": "INR",
        "payment_date": "2026-08-28",
        "payment_method": "IMPS",
        "status": "PENDING"
    })
    bank_txns.append({
        "bank_transaction_id": "BTXN1021",
        "bank_reference": "BANK-8921",
        "amount": 12450.00,
        "transaction_date": "2026-08-28 14:00:00",
        "description": "IMPS REF:BANK-8921 FROM CUST2001",
        "credit_debit": "CREDIT",
        "bank_name": "ICICI Bank"
    })
    invoices.append({
        "invoice_id": "INV-8921",
        "customer_id": "CUST2001",
        "invoice_reference": "INV-8921",
        "invoice_amount": 12000.00,
        "invoice_date": "2026-08-27",
        "due_date": "2026-09-10",
        "currency": "INR",
        "status": "PENDING"
    })
    settlements.append({
        "settlement_id": "SET-1021",
        "transaction_reference": "PAY-8921",
        "gross_amount": 12450.00,
        "fee": 250.0,
        "adjustment": 0.0,
        "net_amount": 12200.00,
        "settlement_date": "2026-08-30",
        "status": "PENDING"
    })

    # 3. Case: Missing Invoice (TXN1022)
    # Payment & Bank exist, Invoice does not
    payments.append({
        "transaction_id": "TXN1022",
        "customer_id": "CUST2002",
        "payment_reference": "REF-NOINV",
        "amount": 3500.0,
        "currency": "INR",
        "payment_date": "2026-08-24",
        "payment_method": "CARD",
        "status": "PENDING"
    })
    bank_txns.append({
        "bank_transaction_id": "BTXN1022",
        "bank_reference": "REF-NOINV",
        "amount": 3500.0,
        "transaction_date": "2026-08-24 16:20:00",
        "description": "CARD REF-NOINV HDFC",
        "credit_debit": "CREDIT",
        "bank_name": "HDFC Bank"
    })
    # Invoice omitted
    settlements.append({
        "settlement_id": "SET-1022",
        "transaction_reference": "REF-NOINV",
        "gross_amount": 3500.0,
        "fee": 70.0,
        "adjustment": 0.0,
        "net_amount": 3430.0,
        "settlement_date": "2026-08-27",
        "status": "PENDING"
    })

    # 4. Case: Missing Payment (Invoice INV-NOPAY)
    # Invoice exists, Payment & Bank do not
    invoices.append({
        "invoice_id": "INV-NOPAY",
        "customer_id": "CUST2003",
        "invoice_reference": "REF-NOPAY",
        "invoice_amount": 7500.00,
        "invoice_date": "2026-08-20",
        "due_date": "2026-09-05",
        "currency": "INR",
        "status": "PENDING"
    })

    # 5. Case: Duplicate Payment (TXN1023A, TXN1023B)
    # Invoice exists for 9000, but there are two payments of 9000
    invoices.append({
        "invoice_id": "INV-DUP",
        "customer_id": "CUST2004",
        "invoice_reference": "REF-DUP",
        "invoice_amount": 9000.00,
        "invoice_date": "2026-08-21",
        "due_date": "2026-09-05",
        "currency": "INR",
        "status": "PENDING"
    })
    payments.append({
        "transaction_id": "TXN1023A",
        "customer_id": "CUST2004",
        "payment_reference": "REF-DUP-1",
        "amount": 9000.00,
        "currency": "INR",
        "payment_date": "2026-08-22",
        "payment_method": "UPI",
        "status": "PENDING"
    })
    payments.append({
        "transaction_id": "TXN1023B",
        "customer_id": "CUST2004",
        "payment_reference": "REF-DUP-2",
        "amount": 9000.00,
        "currency": "INR",
        "payment_date": "2026-08-22",
        "payment_method": "UPI",
        "status": "PENDING"
    })
    bank_txns.append({
        "bank_transaction_id": "BTXN1023A",
        "bank_reference": "REF-DUP-1",
        "amount": 9000.0,
        "transaction_date": "2026-08-22 10:00:00",
        "description": "DUP PAYMENT UPI 1",
        "credit_debit": "CREDIT",
        "bank_name": "SBI"
    })
    bank_txns.append({
        "bank_transaction_id": "BTXN1023B",
        "bank_reference": "REF-DUP-2",
        "amount": 9000.0,
        "transaction_date": "2026-08-22 10:15:00",
        "description": "DUP PAYMENT UPI 2",
        "credit_debit": "CREDIT",
        "bank_name": "SBI"
    })

    # 6. Case: Reference Mismatch (TXN1024)
    # Payment reference = PAY-9999, Bank reference = BANK-9999
    # Amounts are 4500.00, Customer matches. Should trigger fuzzy/rule matching.
    payments.append({
        "transaction_id": "TXN1024",
        "customer_id": "CUST2005",
        "payment_reference": "PAY-9999",
        "amount": 4500.00,
        "currency": "INR",
        "payment_date": "2026-08-23",
        "payment_method": "IMPS",
        "status": "PENDING"
    })
    bank_txns.append({
        "bank_transaction_id": "BTXN1024",
        "bank_reference": "BANK-9999",
        "amount": 4500.00,
        "transaction_date": "2026-08-23 11:30:00",
        "description": "TRANSFER CUST2005 IMPS BANK-9999",
        "credit_debit": "CREDIT",
        "bank_name": "Axis Bank"
    })
    invoices.append({
        "invoice_id": "INV-9999",
        "customer_id": "CUST2005",
        "invoice_reference": "INV-9999",
        "invoice_amount": 4500.00,
        "invoice_date": "2026-08-22",
        "due_date": "2026-09-10",
        "currency": "INR",
        "status": "PENDING"
    })

    # 7. Case: Date Mismatch (TXN1025)
    # Payment date = 2026-08-20, Settlement date = 2026-09-10 (too far apart)
    payments.append({
        "transaction_id": "TXN1025",
        "customer_id": "CUST2006",
        "payment_reference": "REF-DATEMIS",
        "amount": 6000.00,
        "currency": "INR",
        "payment_date": "2026-08-20",
        "payment_method": "UPI",
        "status": "PENDING"
    })
    bank_txns.append({
        "bank_transaction_id": "BTXN1025",
        "bank_reference": "REF-DATEMIS",
        "amount": 6000.00,
        "transaction_date": "2026-08-20 09:00:00",
        "description": "UPI REF-DATEMIS",
        "credit_debit": "CREDIT",
        "bank_name": "HDFC Bank"
    })
    settlements.append({
        "settlement_id": "SET-1025",
        "transaction_reference": "REF-DATEMIS",
        "gross_amount": 6000.00,
        "fee": 120.0,
        "adjustment": 0.0,
        "net_amount": 5880.0,
        "settlement_date": "2026-09-10", # Date drift/mismatch
        "status": "PENDING"
    })

    # 8. Case: Settlement Discrepancy (TXN1026)
    # Gross = 10,000, fee = 200, adjustment = 100, Expected net = 9,700, Actual net = 9,500 (mismatch of 200)
    payments.append({
        "transaction_id": "TXN1026",
        "customer_id": "CUST2007",
        "payment_reference": "REF-SETTDIS",
        "amount": 10000.00,
        "currency": "INR",
        "payment_date": "2026-08-25",
        "payment_method": "UPI",
        "status": "PENDING"
    })
    bank_txns.append({
        "bank_transaction_id": "BTXN1026",
        "bank_reference": "REF-SETTDIS",
        "amount": 10000.00,
        "transaction_date": "2026-08-25 15:00:00",
        "description": "UPI SETTDIS",
        "credit_debit": "CREDIT",
        "bank_name": "ICICI Bank"
    })
    settlements.append({
        "settlement_id": "SET-1026",
        "transaction_reference": "REF-SETTDIS",
        "gross_amount": 10000.00,
        "fee": 200.0,
        "adjustment": 100.0,
        "net_amount": 9500.00, # Expected is 10000 - 200 - 100 = 9700, so discrepancy of 200
        "settlement_date": "2026-08-27",
        "status": "PENDING"
    })

    # Convert to DataFrames and save
    pd.DataFrame(payments).to_csv("sample_data/payments.csv", index=False)
    pd.DataFrame(bank_txns).to_csv("sample_data/bank_transactions.csv", index=False)
    pd.DataFrame(invoices).to_csv("sample_data/invoices.csv", index=False)
    pd.DataFrame(settlements).to_csv("sample_data/settlements.csv", index=False)
    
    print("Sample datasets generated successfully in sample_data/ directory.")

if __name__ == "__main__":
    generate_data()
