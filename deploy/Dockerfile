# Optional container route for the Hostinger VPS.
# The image holds no schedule of its own: the host systemd timers invoke
# `docker compose run --rm monitor ...` through deploy/run_*.sh with SJC_RUNTIME=docker.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Europe/London

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates tzdata \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN python -m pip install --upgrade pip --quiet \
    && python -m pip install -r requirements.txt --quiet

COPY nice_guidance_monitor ./nice_guidance_monitor
COPY data ./data
COPY config.vps.json ./

# config.json, .env, .google_token.json and outputs/ are mounted at run time so
# secrets stay on the host and reports survive image rebuilds.
CMD ["python", "-m", "nice_guidance_monitor.cli", "--config", "config.json"]
