# Only after verifying the base revision, unchanged requirements and original
# API/media Dockerfiles. Replaces every source tree those images execute.
ARG BASE_IMAGE
FROM ${BASE_IMAGE}
COPY apps/api/app/ /app/app/
COPY apps/api/migrations/ /app/migrations/
COPY packages/studio-core/ /app/packages/studio-core/
