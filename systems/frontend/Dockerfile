FROM node:22-bookworm-slim AS build

WORKDIR /workspace/systems/frontend

COPY systems/frontend/package.json systems/frontend/package-lock.json /workspace/systems/frontend/
RUN npm ci --no-audit --no-fund

# Keep the repository-relative frontend depth intact because a small set of
# reference/story modules intentionally import versioned screenshots from
# ../../../../../docs. Flattening systems/frontend to /app breaks those imports
# only inside Docker even though the normal repository build succeeds.
COPY systems/frontend /workspace/systems/frontend
COPY docs /workspace/docs

ARG VITE_API_BASE_URL=http://127.0.0.1:8100
ARG VITE_FEATURE_ONTOLOGY_WORKBENCH=true
ARG VITE_FEATURE_DATASET_CATALOG=false
ARG VITE_FEATURE_GOVERNANCE_WORKBENCH=false
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL} \
    VITE_FEATURE_ONTOLOGY_WORKBENCH=${VITE_FEATURE_ONTOLOGY_WORKBENCH} \
    VITE_FEATURE_DATASET_CATALOG=${VITE_FEATURE_DATASET_CATALOG} \
    VITE_FEATURE_GOVERNANCE_WORKBENCH=${VITE_FEATURE_GOVERNANCE_WORKBENCH}

RUN npm run build

FROM nginx:1.27-alpine AS runtime

COPY systems/frontend/nginx.conf /etc/nginx/nginx.conf
COPY --from=build /workspace/systems/frontend/dist /usr/share/nginx/html

RUN mkdir -p /tmp/nginx /var/cache/nginx /var/run \
    && chown -R 101:101 /tmp/nginx /var/cache/nginx /var/run /usr/share/nginx/html

USER 101

EXPOSE 8080

STOPSIGNAL SIGTERM
CMD ["nginx", "-g", "daemon off;"]
