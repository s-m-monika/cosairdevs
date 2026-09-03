FROM python:3.12-slim

WORKDIR /app

# Install dependencies first (layer-cached unless requirements.txt changes)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source and data
COPY app/ ./app/
COPY data/ ./data/
COPY scripts/ ./scripts/

# Cloud Run injects PORT at runtime (always 8080 on Cloud Run).
# Default to 8080 so local Docker runs also work without extra flags.
ENV PORT=8080

EXPOSE 8080

# Use shell form so $PORT is expanded by the shell at container start.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
