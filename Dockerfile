# syntax=docker/dockerfile:1
# ---- Single-service build for Railway (frontend built as static + served by FastAPI) ----

# Stage 1 — build the React frontend
FROM node:20-alpine AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/yarn.lock ./
RUN corepack enable \
    && corepack prepare yarn@1.22.22 --activate \
    && yarn install --frozen-lockfile --non-interactive --network-timeout 600000
COPY frontend/ ./
# Same-origin API calls in production: REACT_APP_BACKEND_URL stays empty so the
# app calls "/api" on the same host that serves the static files.
ENV REACT_APP_BACKEND_URL=""
ENV DISABLE_ESLINT_PLUGIN=true
ENV CI=false
RUN yarn build

# Stage 2 — Python backend that also serves the built frontend
FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt \
    --extra-index-url https://d33sy5i8bnduwe.cloudfront.net/simple/

COPY backend/ ./backend/
# Bring in the compiled frontend so server.py can serve it (see FRONTEND_BUILD).
COPY --from=frontend /app/frontend/build ./frontend/build

# Railway injects $PORT at runtime; default to 8001 locally.
ENV PORT=8001
EXPOSE 8001
WORKDIR /app/backend
CMD ["sh", "-c", "uvicorn server:app --host 0.0.0.0 --port ${PORT:-8001}"]
