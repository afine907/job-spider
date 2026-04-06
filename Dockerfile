# syntax=docker/dockerfile:1

# ================================
# Stage 1: Builder
# ================================
FROM python:3.12-slim AS builder

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy project files
COPY pyproject.toml .
COPY src/ src/

# Install dependencies using uv
RUN uv pip install --system -e "."

# ================================
# Stage 2: Runtime
# ================================
FROM python:3.12-slim AS runtime

# Labels
LABEL maintainer="job-spider" \
      version="0.1.0" \
      description="Job Spider - Recruitment Data Crawler"

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src:/app \
    PATH="/opt/venv/bin:$PATH"

# Create non-root user
RUN groupadd --gid 1000 spider \
    && useradd --uid 1000 --gid spider --shell /bin/bash --create-home spider

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Create application directories
WORKDIR /app
RUN mkdir -p /app/data /app/logs /app/output \
    && chown -R spider:spider /app

# Copy application code
COPY --chown=spider:spider . .

# Switch to non-root user
USER spider

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Default command
ENTRYPOINT ["python", "main.py"]
CMD ["--help"]
