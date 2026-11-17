FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Sistem paketleri: OpenCV headless için minimum
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 libglib2.0-0 ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-api.txt ./
RUN pip install -r requirements-api.txt

COPY core/ ./core/
COPY api/ ./api/
COPY migrations/ ./migrations/
COPY scripts/ ./scripts/

# Root olarak çalışmaz.
RUN useradd --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser /app
USER appuser

# Render PORT=10000 set eder; yerelde 8000'e düşer.
EXPOSE 8000 10000
CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers"]
