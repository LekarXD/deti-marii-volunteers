FROM node:26-alpine AS build
WORKDIR /app
ARG VITE_APP_BASE_PATH=/
ENV VITE_APP_BASE_PATH=${VITE_APP_BASE_PATH}
RUN npm install --global pnpm@11.3.0
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json ./apps/web/package.json
RUN pnpm install --frozen-lockfile
COPY apps/web/index.html apps/web/recorder.html apps/web/tsconfig.json apps/web/vite.config.ts apps/web/base-path.ts ./apps/web/
COPY apps/web/src/ ./apps/web/src/
COPY apps/web/scripts/ ./apps/web/scripts/
COPY packages/design-tokens/ ./packages/design-tokens/
COPY packages/studio-core/ ./packages/studio-core/
RUN pnpm --filter @opora/web build
FROM nginx:1.29-alpine
COPY infra/docker/nginx.conf /etc/nginx/nginx.conf
COPY --from=build /app/apps/web/dist/ /usr/share/nginx/html/
USER nginx
EXPOSE 8080
