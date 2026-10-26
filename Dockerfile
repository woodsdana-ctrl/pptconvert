# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    HOME=/home/slides PORT=10000
# Optional build secret supports the managed cloud proxy without baking its CA
# into the image. Public hosts use their ordinary verified system trust.
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then export CURL_CA_BUNDLE=/run/secrets/proxy_ca; fi; \
    apt-get update && apt-get install -y --no-install-recommends \
      libreoffice-impress fonts-dejavu-core fonts-liberation ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then export PIP_CERT=/run/secrets/proxy_ca; fi; \
    pip install --no-cache-dir -r requirements.txt
RUN groupadd --gid 10001 slides && useradd --uid 10001 --gid slides --create-home slides \
    && mkdir /app/.runtime && chown slides:slides /app/.runtime
COPY --chown=slides:slides app.py converter.py batch.py ./
COPY --chown=slides:slides static/ ./static/
USER slides
EXPOSE 10000
CMD ["sh", "-c", "exec python -m uvicorn app:app --host 0.0.0.0 --port \"${PORT:-10000}\""]
