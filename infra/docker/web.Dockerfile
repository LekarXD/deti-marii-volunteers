FROM node:26-alpine AS build
WORKDIR /app
RUN npm install --global pnpm@11.3.0
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json ./apps/web/package.json
RUN pnpm install --frozen-lockfile
COPY apps/web/index.html apps/web/tsconfig.json apps/web/vite.config.ts ./apps/web/
COPY apps/web/src/ ./apps/web/src/
RUN pnpm --filter @opora/web build
FROM nginx:1.29-alpine
COPY infra/docker/nginx.conf /etc/nginx/nginx.conf
COPY --from=build /app/apps/web/dist/ /usr/share/nginx/html/
USER nginx
EXPOSE 8080
