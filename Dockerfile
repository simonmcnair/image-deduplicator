# Multi-stage build for smaller final image
FROM python:3.11-slim AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Final stage
FROM python:3.11-slim

# Install runtime dependencies for image processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    libjpeg62-turbo \
    libpng16-16 \
    libtiff6 \
    libwebp7 \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Set working directory
WORKDIR /app

# Copy application files
COPY image_deduplicate.py .
COPY web_ui.py .
COPY templates ./templates

# Create volume mount points for image directories, state persistence, and database
VOLUME ["/data", "/state", "/app/data"]

# Expose web UI port
EXPOSE 5000

# Set user to non-root for security
RUN useradd -m -u 1000 dedup && \
    chown -R dedup:dedup /app && \
    mkdir -p /app/data && \
    chown -R dedup:dedup /app/data
USER dedup

# Set default command (CLI mode)
ENTRYPOINT ["python", "image_deduplicate.py"]
CMD ["/data"]

# To run web UI instead, use:
# docker run -p 5000:5000 image-deduplicator python web_ui.py

# Health check (validates Python environment)
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import imagehash, PIL, flask; print('OK')" || exit 1

# Labels
LABEL description="Advanced Image Deduplication Tool with Perceptual Hashing and Resume Capability"
LABEL version="2.0.0"
LABEL org.opencontainers.image.source="https://github.com/simonmcnair/image-deduplicator"
LABEL org.opencontainers.image.licenses="MIT"
