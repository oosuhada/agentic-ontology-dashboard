FROM node:22-bookworm-slim AS build

WORKDIR /app

COPY web/package.json web/package-lock.json /app/
RUN npm ci --no-audit --no-fund

COPY web /app

ARG VITE_API_BASE_URL=http://127.0.0.1:8100
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}

RUN npm run build

FROM nginx:1.27-alpine AS runtime

COPY web/nginx.conf /etc/nginx/nginx.conf
COPY --from=build /app/dist /usr/share/nginx/html

RUN mkdir -p /tmp/nginx /var/cache/nginx /var/run \
    && chown -R 101:101 /tmp/nginx /var/cache/nginx /var/run /usr/share/nginx/html

USER 101

EXPOSE 8080

STOPSIGNAL SIGTERM
CMD ["nginx", "-g", "daemon off;"]
