FROM node:26-alpine AS build
WORKDIR /app
RUN corepack enable && corepack prepare pnpm@11.3.0 --activate
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json ./apps/web/package.json
RUN pnpm install --frozen-lockfile
COPY apps/web/ ./apps/web/
RUN pnpm --filter @opora/web build
FROM nginx:1.29-alpine
COPY infra/docker/nginx.conf /etc/nginx/nginx.conf
COPY --from=build /app/apps/web/dist/ /usr/share/nginx/html/
USER nginx
EXPOSE 8080
