FROM python:3.13-slim

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        ffmpeg \
        ca-certificates \
        curl \
        tzdata \
    && rm -rf /var/lib/apt/lists/* \
    && curl -fsSL -o /usr/local/bin/supercronic \
        https://github.com/aptible/supercronic/releases/download/v0.2.33/supercronic-linux-amd64 \
    && chmod +x /usr/local/bin/supercronic

WORKDIR /opt/ivr-farmacias/web
COPY web/requirements.txt /opt/ivr-farmacias/web/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY web /opt/ivr-farmacias/web
COPY docker/web/crontab /opt/ivr-farmacias/crontab

ENV IVR_ENV=production \
    PYTHONUNBUFFERED=1

EXPOSE 8787
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8787"]
