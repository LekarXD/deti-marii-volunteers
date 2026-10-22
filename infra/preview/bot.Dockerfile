FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 DB_PATH=/var/lib/opora-bot/bot.db
WORKDIR /app
COPY bot/requirements.txt /app/requirements.txt
RUN pip install -r requirements.txt && useradd --create-home --uid 10001 opora \
    && mkdir -p /var/lib/opora-bot && chown opora:opora /var/lib/opora-bot
COPY bot/opora_bot/ /app/opora_bot/
COPY bot/email_templates/ /app/email_templates/
USER 10001:10001
CMD ["python", "-m", "opora_bot"]
