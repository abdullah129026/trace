# Trace backend: FastAPI + Python tracer + Node JS tracer in one image.
# Render builds this with dockerContext backend/, so COPY paths are
# relative to backend/. Node 20 matches the CI setup; the JS sandbox
# needs a real node binary (nodesource installs it at /usr/bin/node,
# which is on the sandbox child's PATH).

FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY app ./app

WORKDIR /app/app/js_driver
RUN npm ci --omit=dev

WORKDIR /app
RUN useradd --create-home app \
    && chown -R app:app /app
USER app

EXPOSE 8000

# Render sets PORT; default keeps local `docker run` working.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
