# Node toolchain that builds the /deti-marii web app on the preview host (same versions as CI).
FROM node:26-slim
RUN npm install --global pnpm@11.3.0 && npm cache clean --force
