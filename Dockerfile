# ==================================================================================
# PRODUCTION-READY DOCKERFILE FOR MARKER3 WITH RTX 5090 SUPPORT
# ==================================================================================
# Features:
# - NVIDIA CUDA 12.8+ for RTX 5090 Blackwell architecture compatibility  
# - Clean multi-stage build with shared Python base
# - Security hardening with non-root user
# - System dependencies for PDF/OCR processing
# - Optimized layer caching and minimal redundancy
# ==================================================================================

# Shared Base: Python + CUDA Foundation
# ----------------------------------------------------------------------
FROM nvidia/cuda:12.8.0-runtime-ubuntu22.04 as python-cuda-base

# Security: Update system packages to patch CVEs
RUN apt-get update && apt-get upgrade -y

# Install Python 3.11 once for both stages
RUN apt-get install -y \
    python3.11 \
    python3.11-dev \
    python3.11-venv \
    python3-pip \
    curl \
    && ln -sf /usr/bin/python3.11 /usr/bin/python \
    && ln -sf /usr/bin/python3.11 /usr/bin/python3 \
    && rm -rf /var/lib/apt/lists/*

# Stage 1: The Builder (Dependencies + Build)
# ----------------------------------------------------------------------
FROM python-cuda-base as builder

# Install build tools (only needed for building)
RUN apt-get update && apt-get install -y \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install system dependencies for marker3 document processing
RUN apt-get update && apt-get install -y \
    poppler-utils \
    tesseract-ocr \
    tesseract-ocr-eng \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    libgdk-pixbuf2.0-0 \
    libfontconfig1 \
    libxrender1 \
    libxtst6 \
    libxi6 \
    libxrandr2 \
    libasound2 \
    && rm -rf /var/lib/apt/lists/*

# Set up Poetry with optimized configuration
ENV POETRY_HOME=/usr/local/poetry \
    POETRY_CACHE_DIR=/tmp/poetry_cache \
    PATH="$POETRY_HOME/bin:$PATH"

RUN pip install poetry==1.8.3
RUN poetry config virtualenvs.in-project true
RUN poetry config cache-dir $POETRY_CACHE_DIR

WORKDIR /app

# Copy dependency files FIRST for optimal Docker layer caching
COPY pyproject.toml poetry.lock ./

# Install dependencies in virtual environment
RUN poetry install --only=main --extras=full && rm -rf $POETRY_CACHE_DIR

# Copy source code AFTER dependencies are installed
COPY . .

# Install the marker package itself into the virtual environment
# This creates the CLI scripts (marker, marker_single, etc.) in .venv/bin/
RUN poetry install --only-root

# Upgrade PyTorch to RTX 5090-compatible version with CUDA 12.8 support
# IMPORTANT: This must come AFTER poetry install --only-root to prevent Poetry from reverting it
RUN /app/.venv/bin/pip install --upgrade torch==2.7.0 torchvision==0.22.0 torchaudio==2.7.0 --index-url https://download.pytorch.org/whl/cu128

# Stage 2: The Runtime (Clean Production Image)
# ----------------------------------------------------------------------
FROM python-cuda-base as runtime

# Install only runtime system dependencies (no build tools)
RUN apt-get update && apt-get install -y \
    poppler-utils \
    tesseract-ocr \
    tesseract-ocr-eng \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libgomp1 \
    libgdk-pixbuf2.0-0 \
    libfontconfig1 \
    libxrender1 \
    && rm -rf /var/lib/apt/lists/*

# Security: Create non-root user
RUN groupadd --gid 1000 appuser \
    && useradd --uid 1000 --gid appuser --shell /bin/bash --create-home appuser

# Set up application directory with proper permissions
WORKDIR /app
RUN chown -R appuser:appuser /app

# Copy the complete virtual environment from builder
COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv

# Copy only the application source code (not build artifacts)
COPY --from=builder --chown=appuser:appuser /app/marker /app/marker
COPY --from=builder --chown=appuser:appuser /app/pyproject.toml /app/pyproject.toml
COPY --from=builder --chown=appuser:appuser /app/scripts /app/scripts

# Runtime optimizations
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH="/app:$PYTHONPATH" \
    # CUDA optimizations for RTX 5090
    CUDA_VISIBLE_DEVICES=0 \
    NVIDIA_VISIBLE_DEVICES=all \
    NVIDIA_DRIVER_CAPABILITIES=compute,utility

# Switch to non-root user for security
USER appuser

# Create directories for models and data with proper permissions
RUN mkdir -p /app/models /app/data /app/output

# Health check to ensure the application is responsive
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import marker; print('Marker is ready')" || exit 1

# Expose port for potential web interface
EXPOSE 8000

# Default command - can be overridden
CMD ["python", "-m", "marker.scripts.server"]
