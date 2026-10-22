# Release web image: the fixed full-build Nginx base with this commit's /deti-marii build.
ARG BASE_IMAGE
FROM ${BASE_IMAGE}
USER root
RUN rm -rf /usr/share/nginx/html
COPY dist/ /usr/share/nginx/html/
USER nginx
