# Audio Processing System - Production Dockerfile
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install system dependencies for audio processing
RUN apt-get update && apt-get install -y \
    portaudio19-dev \
    libasound2-dev \
    libsndfile1-dev \
    ffmpeg \
    gcc \
    g++ \
    make \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY src/ ./src/
COPY config/ ./config/
COPY static/ ./static/

# Create necessary directories
RUN mkdir -p /app/logs /app/recordings /app/plugins

# Set Python path
ENV PYTHONPATH=/app/src

# Create non-root user for security
RUN useradd -m -u 1000 audiouser && \
    chown -R audiouser:audiouser /app
USER audiouser

# Expose ports
EXPOSE 8000 8001

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Default command
CMD ["python", "-m", "uvicorn", "audio_processing.web.main:app", "--host", "0.0.0.0", "--port", "8000"]