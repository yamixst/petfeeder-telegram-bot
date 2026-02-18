# -- Stage 1: build dependencies --
FROM python:3.12-slim AS builder

WORKDIR /build

COPY requirements.txt .

RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# -- Stage 2: runtime image --
FROM python:3.12-slim

LABEL maintainer="petfeeder-bot"
LABEL description="Telegram bot for controlling a Tuya-based automatic pet feeder"

# Create non-root user
RUN groupadd --gid 1000 appuser \
    && useradd --uid 1000 --gid appuser --shell /bin/false --create-home appuser

# Copy installed packages from builder stage
COPY --from=builder /install /usr/local

# Set working directory
WORKDIR /app

# Copy application source
COPY petfeeder_bot.py .

# Create logs directory and set ownership
RUN mkdir -p /app/logs && chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Health check — verify the process is alive
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD pgrep -f petfeeder_bot.py > /dev/null || exit 1

ENTRYPOINT ["python", "-u", "petfeeder_bot.py"]
