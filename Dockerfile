FROM python:3.11-slim

# Prevent Python from writing bytecode and enable unbuffered streaming
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

# Install curl for container health check probes
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Create non-root system user and group
RUN groupadd -r revpulse && useradd -r -g revpulse -d /app -s /sbin/nologin revpulse

# Copy application source code and configuration
COPY . .

# Set proper ownership for non-root runtime
RUN chown -R revpulse:revpulse /app

# Switch to non-root user
USER revpulse

# Expose API port
EXPOSE 8000

# Container health check probe
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Launch production ASGI server
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
