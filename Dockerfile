# ═══════════════════════════════════════════════════════════════════════════
# OmniBrain — Multi-Stage Production Dockerfile
# "Your AI must be yours."
#
# Usage:
#   docker compose up              → full stack (backend + frontend)
#   docker compose --profile local → + Ollama for local LLM
#
# Design decisions:
#   - Multi-stage build minimises image size (~400MB vs ~2GB)
#   - Backend and frontend in one container (simplifies networking)
#   - ~/.omnibrain mounted as volume for persistent data
#   - Supervisord orchestrates backend + frontend processes
#   - Health check on backend /api/v1/health endpoint
# ═══════════════════════════════════════════════════════════════════════════

# ── Stage 1: Python Backend Builder ──────────────────────────────────────
FROM python:3.12-slim AS python-builder

WORKDIR /build

# System deps for building Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md LICENSE ./
COPY src/ src/

# Install in a virtualenv for clean layer separation
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir -e ".[all]"


# ── Stage 2: Frontend Builder ────────────────────────────────────────────
FROM node:20-slim AS frontend-builder

WORKDIR /build/web

COPY web/package.json web/package-lock.json* ./
RUN npm ci --prefer-offline --no-audit --no-fund 2>/dev/null || npm install --no-audit --no-fund

COPY web/ ./

# Build Next.js in standalone mode for production
ENV NEXT_TELEMETRY_DISABLED=1
ENV OMNIBRAIN_API_HOST=127.0.0.1
ENV OMNIBRAIN_API_PORT=7432
RUN npm run build


# ── Stage 3: Runtime ─────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

LABEL maintainer="Francesco Stabile"
LABEL description="OmniBrain — Open-source AI that works for you"
LABEL org.opencontainers.image.source="https://github.com/FrancescoStabile/omnibrain"

# Install Node.js (for Next.js runtime) + supervisor
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    supervisor \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy Python virtualenv from builder
COPY --from=python-builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Copy Python source
COPY --from=python-builder /build/src /app/src
COPY --from=python-builder /build/pyproject.toml /app/

# Copy built frontend
COPY --from=frontend-builder /build/web/.next /app/web/.next
COPY --from=frontend-builder /build/web/public /app/web/public
COPY --from=frontend-builder /build/web/package.json /app/web/
COPY --from=frontend-builder /build/web/node_modules /app/web/node_modules
COPY --from=frontend-builder /build/web/next.config.ts /app/web/

# Copy skills
COPY skills/ /app/skills/

# Create data directory
RUN mkdir -p /data/omnibrain

# Supervisord configuration — runs backend + frontend
COPY docker/supervisord.conf /etc/supervisor/conf.d/omnibrain.conf

# Environment defaults
ENV OMNIBRAIN_DATA_DIR=/data/omnibrain
ENV OMNIBRAIN_API_HOST=0.0.0.0
ENV OMNIBRAIN_API_PORT=7432
ENV OMNIBRAIN_FRONTEND_PORT=3000

# Expose ports
EXPOSE 7432 3000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -sf http://127.0.0.1:7432/api/v1/health || exit 1

# Entrypoint: supervisord manages both processes
CMD ["supervisord", "-c", "/etc/supervisor/conf.d/omnibrain.conf", "-n"]
