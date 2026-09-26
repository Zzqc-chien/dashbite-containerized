# One image for every DashBite stage and for the in-image test run.
# Each Compose service overrides the command; the default runs the dashboard.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    DATA_ROOT=/data \
    HEARTBEAT_DIR=/tmp/dashbite \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependencies first, so code edits reuse this layer.
COPY requirements.txt .
RUN pip install -r requirements.txt

# Unprivileged user. /data must exist in the image and belong to app:
# Docker copies it (owner included) into a fresh named volume on first mount.
RUN useradd --uid 10001 --user-group --create-home --shell /usr/sbin/nologin app \
    && mkdir -p /data \
    && chown app:app /data

COPY pipeline/ pipeline/
COPY tests/ tests/
COPY pytest.ini .

USER app

EXPOSE 8501

# Exec form: Streamlit is PID 1 and receives SIGTERM directly.
CMD ["streamlit", "run", "pipeline/dashboard/app.py", \
     "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true"]
