FROM python:3.11-slim

# Build deps for asyncpg (libpq) and chromadb (sqlite3, native extensions)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc g++ build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy entire server directory
COPY . .

# DATA_DIR=/app/data so ChromaDB and other persistent data use the in-image path.
# On Fly.io, mount a volume at /app/data to persist across deploys.
ENV DATA_DIR=/app/data
ENV PORT=8000

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
