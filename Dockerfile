# Tendrill Backend Dockerfile
# Python 3.12 + FastAPI

FROM python:3.12-slim

# Labels
LABEL maintainer="kurzschlusskind"
LABEL description="Tendrill - Grow Monitoring System"

# Environment
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# System Dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Working Directory
WORKDIR /app

# Copy Dependency Files
COPY pyproject.toml ./

# Install Dependencies
RUN pip install --upgrade pip && \
    pip install .

# Copy Application Code
COPY src/ ./src/
COPY data/ ./data/

# Create non-root user
RUN useradd --create-home --shell /bin/bash tendrill && \
    chown -R tendrill:tendrill /app

USER tendrill

# Expose Port
EXPOSE 8000

# Health Check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run Application
CMD ["uvicorn", "tendrill.main:app", "--host", "0.0.0.0", "--port", "8000"]
