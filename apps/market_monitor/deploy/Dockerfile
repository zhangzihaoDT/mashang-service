FROM python:3.13-slim
WORKDIR /opt/market-monitor
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MARKET_MONITOR_SNAPSHOT_DIR=/var/lib/market-monitor \
    GUNICORN_CMD_ARGS="--bind=0.0.0.0:80"
RUN pip install --no-cache-dir gunicorn==23.0.0
COPY backend/__main__.py backend/snapshot.py backend/web.py apps/market_monitor/backend/
COPY configs/sources.json apps/market_monitor/configs/
COPY frontend/index.html frontend/app.css frontend/app.js apps/market_monitor/frontend/
USER 10001:10001
EXPOSE 80
CMD ["gunicorn", "--workers=2", "apps.market_monitor.backend.web:create_app()"]
