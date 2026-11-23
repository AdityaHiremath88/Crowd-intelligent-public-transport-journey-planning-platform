FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
RUN useradd --create-home --uid 10001 yuktix \
    && mkdir -p /app/datasets/processed /app/datasets/community \
    && chown -R yuktix:yuktix /app
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY backend_v2 ./backend_v2

USER yuktix
EXPOSE 8002
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8002/api/v2/health', timeout=3)" || exit 1
CMD ["uvicorn", "backend_v2.main:app", "--host", "0.0.0.0", "--port", "8002"]
