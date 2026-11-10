# ---- 1. Frontend build ------------------------------------------------------
FROM node:22-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- 2. Backend + headless Chromium for validation -------------------------
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    NGUI_PORT=8200
WORKDIR /app

COPY backend/requirements.txt backend/requirements-ocr.txt backend/
RUN pip install -r backend/requirements.txt \
 && (pip install -r backend/requirements-ocr.txt || echo "optional OCR not installed") \
 && python -m playwright install --with-deps chromium \
 && rm -rf /var/lib/apt/lists/*

COPY backend/ backend/
COPY dataset/ dataset/
COPY evaluation/ evaluation/
COPY docs/ docs/
COPY --from=frontend /app/frontend/dist frontend/dist

WORKDIR /app/backend
RUN mkdir -p data
VOLUME ["/app/backend/data"]
EXPOSE 8200
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8200/api/health', timeout=4)"
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8200"]
