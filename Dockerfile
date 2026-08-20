# ─────────────────────────────────────────────────────────────
# Marg API Gateway — Production Container Image
# ─────────────────────────────────────────────────────────────
FROM python:3.12-slim

# Build args
ARG MARG_VERSION=0.1.0

# Metadata
LABEL org.opencontainers.image.title="Marg API Gateway"
LABEL org.opencontainers.image.description="India-scoped self-hosted mapping & routing engine"
LABEL org.opencontainers.image.version="${MARG_VERSION}"

# Security: run as non-root user
RUN groupadd --gid 1001 marg && \
    useradd --uid 1001 --gid marg --shell /bin/bash --create-home marg

WORKDIR /app

# Install system dependencies (minimal)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files first (layer caching)
COPY pyproject.toml ./

# Install Python dependencies (production only — no dev extras)
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -e "."

# Copy application source
COPY marg/ ./marg/

# Create data directory (mounted as volume at runtime)
RUN mkdir -p /app/data && chown -R marg:marg /app

# Switch to non-root
USER marg

EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

# Run the API server
CMD ["python", "-m", "uvicorn", "marg.api.main:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--log-level", "info", "--no-access-log"]
