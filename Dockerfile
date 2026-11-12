# Image minimale, utilisateur non-root. Build : docker build -t goutte-deau .
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-deps .
RUN useradd --create-home appuser && mkdir -p /data /models && chown -R appuser /data /models
USER appuser
ENV GD_DB_PATH=/data/goutte_deau.db GD_MODEL_DIR=/models GD_REPORT_DIR=/data/reports
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health').status==200 else 1)"
CMD ["uvicorn", "goutte_deau.api:app", "--host", "0.0.0.0", "--port", "8000"]
