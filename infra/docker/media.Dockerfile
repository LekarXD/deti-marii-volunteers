# Matches the exact runtime package, including full Chrome for Testing.
FROM mcr.microsoft.com/playwright:v1.58.2-noble
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    PATH=/opt/opora-python/bin:$PATH \
    NODE_PATH=/opt/opora-media/node_modules \
    OPORA_ASSET_ROOT=/var/lib/opora/assets \
    OPORA_CAPTURE_CHROME_PATH=/usr/local/bin/opora-capture-chrome \
    HOME=/home/opora TMPDIR=/tmp
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3.12 python3.12-venv ffmpeg libreoffice-impress \
    && rm -rf /var/lib/apt/lists/* \
    && python3.12 -m venv /opt/opora-python \
    && useradd --create-home --uid 10001 opora
COPY infra/docker/media-package.json /opt/opora-media/package.json
COPY infra/docker/media-package-lock.json /opt/opora-media/package-lock.json
RUN cd /opt/opora-media && npm ci --omit=dev --ignore-scripts \
    && node -e "if(Number(process.versions.node.split('.')[0])<22)process.exit(1);if(require('playwright/package.json').version!=='1.58.2')process.exit(1)" \
    && ln -s "$(node -p 'require("playwright").chromium.executablePath()')" /usr/local/bin/opora-capture-chrome \
    && test -x /usr/local/bin/opora-capture-chrome
WORKDIR /app
COPY apps/api/pyproject.toml apps/api/requirements.lock apps/api/alembic.ini ./
COPY apps/api/app/ ./app/
COPY apps/api/migrations/ ./migrations/
COPY packages/studio-core/ ./packages/studio-core/
RUN pip install -r requirements.lock && pip install --no-deps . \
    && mkdir -p /var/lib/opora/assets \
    && chown opora:opora /var/lib/opora/assets \
    && chmod 0700 /var/lib/opora/assets
USER 10001:10001
# Source-controlled kinds only. Ordinary outbox/AI jobs run in other workers.
CMD ["python", "-m", "app.worker.main", "--kind", "slides.convert", "--kind", "recording.capture"]
