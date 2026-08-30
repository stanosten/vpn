# ==========================================
# Dockerfile for Async IP & VPN Node Checker
# ==========================================

FROM python:3.11-slim

# Set work directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Create data directories
RUN mkdir -p data/input data/output logs

# Expose Web & API Port
EXPOSE 8000

# Default command: launch Web UI & REST API
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
