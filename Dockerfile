FROM node:22-alpine AS frontend-build
WORKDIR /build/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
RUN useradd --create-home --shell /bin/bash purvai
WORKDIR /app

COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend ./backend
COPY config ./config
COPY --from=frontend-build /build/frontend/dist ./frontend/dist

RUN chown -R purvai:purvai /app
USER purvai
WORKDIR /app/backend

ENV PURVAI_MODE=demo \
    TRUST_PROXY_HEADERS=true \
    PYTHONUNBUFFERED=1

EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --proxy-headers --forwarded-allow-ips='*'"]
