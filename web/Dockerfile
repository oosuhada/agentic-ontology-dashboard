FROM node:22-bookworm-slim

WORKDIR /app

COPY web/package.json /app/package.json
RUN npm install --no-audit --no-fund

COPY web /app

ARG VITE_API_BASE_URL=http://127.0.0.1:8100
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}

RUN npm run build

EXPOSE 3100

CMD ["npx", "vite", "preview", "--host", "0.0.0.0", "--port", "3100", "--strictPort"]
