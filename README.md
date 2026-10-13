# ReconAI --- AI-Powered Financial Reconciliation & Exception Management Platform

ReconAI is a complete, enterprise-grade prototype for automating financial reconciliation across payments transactions, bank statements, invoices, and processor settlement records. It combines deterministic financial engines, fuzzy similarity matchers, trained machine learning probability models, and LLM-driven exception investigations to reduce manual reconciliation workloads.

---

## 1. Project Overview

ReconAI processes complex transaction flows to align:
1. **Payments Transactions:** Internal records of customer checkout attempts.
2. **Bank Statements:** External reports of physical money received.
3. **Invoices:** Internal records of customer billing obligations.
4. **Processor Settlements:** Settlement fee/adjustment logs from Stripe, Razorpay, etc.

By matching these records, ReconAI detects exact clearings, identifies discrepancies, triggers structured LLM forensic reviews on errors, and updates operational dashboards automatically.

---

## 2. Problem Statement

Finance teams struggle to reconcile fragmented data feeds. Basic database equality matches fail on:
- **Discrepant Amounts:** Gateway processing fees deducted prior to settlement.
- **Reference Mismatches:** Typos and prefix disparities between systems (e.g. `PAY-8921` vs `BANK-8921`).
- **Timing Differences:** Delays between payment authorization and bank clearing.
- **Duplicate Charges & Fraud:** Dual execution of API checks.

ReconAI isolates these anomalies, calculates a confidence score, and routes exception evidence to an AI Forensic Investigator for analysis.

---

## 3. System Architecture

The core architecture follows a layered pipeline design:

```
                  +----------------------------------+
                  |  Ingestion (CSV/JSON upload API)  |
                  +-----------------+----------------+
                                    |
                                    v
                  +-----------------+----------------+
                  |  Normalization (clean references |
                  |  amounts, and dates in service)  |
                  +-----------------+----------------+
                                    |
                                    v
                  +-----------------+----------------+
                  |          Matching Engine         |
                  |  - Level 1: Exact matches        |
                  |  - Level 2: Weighted rules       |
                  |  - Level 3: RapidFuzz strings    |
                  |  - Level 4: ML RF Matcher        |
                  +-----------------+----------------+
                                    |
                                    v
                  +-----------------+----------------+
                  |        Confidence Score          |
                  +--------+----------------+--------+
                           |                |
             (score >= 98) |                | (60 <= score < 98)
                           v                v
                 +---------+---+   +--------+---------+
                 | Auto-Match  |   | Raise Exception  |
                 | (Reconciled)|   |  (Queue for AI)  |
                 +-------------+   +--------+---------+
                                            |
                                            v
                                   +--------+---------+
                                   |  AI Investigation|
                                   |  (Gemini API/    |
                                   |  Fallback rules) |
                                   +--------+---------+
                                            |
                                            v
                                   +--------+---------+
                                   |   Human Review   |
                                   |   & Audit Logs   |
                                   +------------------+
```

---

## 4. Key Features

- **Multi-Level Matching:** Exact key checking, weighted logic scores, RapidFuzz string distance, and trained Random Forest model evaluations.
- **Automated Exception Detection:** Catches `AMOUNT_MISMATCH`, `MISSING_INVOICE`, `MISSING_PAYMENT`, `DUPLICATE_PAYMENT`, `REFERENCE_MISMATCH`, `DATE_MISMATCH`, and `SETTLEMENT_DISCREPANCY`.
- **AI Investigation Agent:** Plugs structured evidence into Gemini API for root-cause synthesis and actions fallback.
- **Human-in-the-Loop Reviews:** UI forms to allow manual confirmations, overrides, and escalations.
- **Data Quality & Drift Monitoring:** Evident-based tracking of incoming formats, missing properties, and statistical mean value changes.
- **AI Finance Copilot:** An assistant that compiles database summaries from natural language prompts.

---

## 5. Technology Stack

- **Backend:** Python 3.11+, FastAPI, Pydantic V2, SQLAlchemy.
- **Data & ML:** Pandas, NumPy, RapidFuzz, Scikit-learn, joblib.
- **Database:** SQLite (local prototype default) / PostgreSQL (production docker compose).
- **Monitoring:** Evidently.
- **Frontend:** React 18, TypeScript, Tailwind CSS, Recharts, Lucide Icons, Vite.
- **Deployment:** Docker, Docker Compose.

---

## 6. Setup Instructions (Local Development)

### Backend Setup
1. Clone the project and navigate to the project directory:
   ```bash
   cd c:/RazorPay
   ```
2. Set up virtual environment and activate:
   ```bash
   python -m venv venv
   # Windows:
   venv\Scripts\activate
   ```
3. Install required packages:
   ```bash
   pip install -r requirements.txt
   ```
4. Start the development server:
   ```bash
   uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

### Frontend Setup
1. Navigate to the frontend directory:
   ```bash
   cd frontend
   ```
2. Install npm modules:
   ```bash
   npm install
   ```
3. Boot Vite webserver:
   ```bash
   npm run dev
   ```
4. Open your browser to `http://localhost:5173`.

---

## 7. Environment Variables

Create a `.env` file at the root directory:
```env
# API Keys (optional; falls back to deterministic analysis if empty)
GEMINI_API_KEY=your_gemini_api_key_here

# Database URL
# Defaults to SQLite local file: sqlite:///./reconai.db
DATABASE_URL=sqlite:///./reconai.db

# Engine Configurations
ML_MODEL_PATH=ml/artifacts/matcher_model.joblib
```

---

## 8. Database Setup

ReconAI creates database tables dynamically on application startup via SQLAlchemy.
To seed initial datasets for testing, run the sample data generator:
```bash
python sample_data/generate_sample_data.py
```
This generates payment, bank statement, invoice, and settlement CSVs under `sample_data/`.

---

## 9. Machine Learning Training Instructions

To train or refresh the Level 4 Machine Learning matching model:
1. Ensure the sample data CSVs are generated.
2. Execute the training script:
   ```bash
   python ml/training/train.py
   ```
3. This will parse matches, extract features (`amount_ratio`, `date_diff`, `reference_similarity`), fit a Scikit-learn `RandomForestClassifier`, and save the compiled model as `ml/artifacts/matcher_model.joblib`.

---

## 10. API Documentation

Access Swagger documentation at `http://localhost:8000/docs` when the backend is running.
Key API routes:
- `POST /api/v1/ingestion/payments`: Ingest payments.
- `POST /api/v1/ingestion/bank-statements`: Ingest bank statements.
- `POST /api/v1/ingestion/invoices`: Ingest invoices.
- `POST /api/v1/ingestion/settlements`: Ingest settlements.
- `POST /api/v1/reconciliation/run`: Executes matching pipelines.
- `GET /api/v1/reconciliation/summary`: Returns summary KPIs.
- `GET /api/v1/exceptions`: Returns list of unresolved anomalies.
- `POST /api/v1/investigation/{exception_id}`: Triggers AI forensic agent.
- `POST /api/v1/decisions/{exception_id}`: Persists human reviewer resolutions.
- `GET /api/v1/monitoring`: Returns data quality and Evidently reports.
- `POST /api/v1/copilot/query`: Triggers copilot response.

---

## 11. Frontend Setup

The frontend is built using **Vite + React + TS + Tailwind CSS**. It contains state-managed operational dashboards, exception tables, a natural language input card, and Evidently performance reports.

---

## 12. Docker Setup

To orchestrate the system in a production container stack (which sets up Postgres, backend, and Nginx frontend containers):
1. Make sure Docker is installed.
2. Spin up containers from the root directory:
   ```bash
   docker-compose up --build
   ```
3. Access the application on port 80: `http://localhost`.

---

## 13. Testing

Pytest is used for unit and integration testing.
1. Run the test suite:
   ```bash
   pytest
   ```
This validates normalizations, matching confidence, duplicate exceptions, and simulates an E2E audit ledger loop.

---

## 14. Example Workflow

1. **Ingest data:** Upload payment, bank statement, and invoice files via the UI.
2. **Execute reconciler:** Click 'Start Matching'. Most transactions are matched at 100% confidence.
3. **Isolate exceptions:** Transaction `TXN1021` matches bank at high score, but invoice amount is ₹12,000 while payment is ₹12,450.
4. **Trigger AI Forensics:** Select `TXN1021` in Exceptions, click 'Analyze Discrepancy'. AI isolates the ₹450 gap, notes causes, and recommends review.
5. **Persist Decision:** Auditor selects `MARK_EXCEPTION`, inputs comments, and submits. Payment updates to exception and audit logs record the action.

---

## 15. Limitations

- **Currency conversions:** Currency matching currently assumes matches belong to the same reference currency unless explicitly defined in conversion metadata.
- **Unlabeled ML pairs:** The ML matcher requires initial deterministic label matching flags to compile positive and negative pairs.

---

## 16. Future Improvements

- Add Multi-Currency exchange-rate converters inside the normalization pipeline.
- Implement streaming reconciliation via WebSockets or Kafka queues for live transaction streaming.
