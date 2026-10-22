# Release image for API/workers and media: a fixed full-build base plus this commit's
# Python source trees. opora_deploy.py uses it only while every dependency input of the
# base build is unchanged. Old trees are removed first so deleted modules and
# migrations do not survive from the base.
ARG BASE_IMAGE
FROM ${BASE_IMAGE}
ARG RUNTIME_USER
USER root
RUN rm -rf /app/app /app/migrations /app/packages/studio-core
COPY apps/api/app/ /app/app/
COPY apps/api/migrations/ /app/migrations/
COPY packages/studio-core/ /app/packages/studio-core/
USER ${RUNTIME_USER}
