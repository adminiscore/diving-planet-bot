FROM python:3.11-slim

WORKDIR /app

# System dependencies for building Python packages (asyncpg, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (layer cache)
COPY pyproject.toml README.md .
COPY src/ src/
RUN pip install --no-cache-dir .

# Copy data and scripts (not needed for pip install but useful inside container)
COPY data/ data/
COPY scripts/ scripts/

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["python", "-m", "src.main"]
