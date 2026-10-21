FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY apps/api/app/integrations/rtc/sidecar/requirements.txt /app/requirements.txt
RUN pip install -r requirements.txt && useradd --create-home --uid 10001 opora \
    && mkdir -p /var/lib/opora/board && chown opora:opora /var/lib/opora/board
COPY apps/api/app/integrations/rtc/sidecar/ /app/app/integrations/rtc/sidecar/
USER 10001:10001
CMD ["python", "-m", "app.integrations.rtc.sidecar", "--host", "0.0.0.0", "--port", "7881"]
