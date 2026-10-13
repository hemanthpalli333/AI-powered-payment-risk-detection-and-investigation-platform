FROM python:3.11-slim

WORKDIR /app

# Install system dependencies needed for compiling rapidfuzz or other packages if needed
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements.txt from root
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend codebase
COPY backend/ ./backend/
COPY ml/ ./ml/
COPY sample_data/ ./sample_data/

# Environment variables defaults
ENV PYTHONPATH=/app
ENV DATABASE_URL=sqlite:///./reconai.db

EXPOSE 8000

# Run uvicorn on startup
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
