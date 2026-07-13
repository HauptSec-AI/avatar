# Avatar - single container: Vite-built frontend served by FastAPI.

# ---- Frontend build ----
FROM node:22-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# ---- Backend runtime ----
FROM python:3.12-slim AS backend
RUN pip install --no-cache-dir uv
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/ .
RUN uv sync --frozen --no-dev

WORKDIR /app
COPY knowledge/ ./knowledge/
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

RUN useradd --create-home --uid 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
CMD ["uv", "run", "--project", "backend", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--app-dir", "backend"]
