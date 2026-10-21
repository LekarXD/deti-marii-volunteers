FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY apps/api/pyproject.toml apps/api/requirements.lock apps/api/alembic.ini ./
COPY apps/api/app/ ./app/
COPY apps/api/migrations/ ./migrations/
COPY packages/studio-core/ ./packages/studio-core/
RUN pip install -r requirements.lock && pip install --no-deps . && useradd --create-home --uid 10001 opora \
    && mkdir -p /var/lib/opora/assets && chown opora:opora /var/lib/opora/assets
USER opora
EXPOSE 8001
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001", "--no-access-log"]
