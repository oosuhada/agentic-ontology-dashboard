# Current MVP infrastructure

The retained infrastructure runs only the current React application, FastAPI service and Canonical V3.1 PostgreSQL runtime. Redis is optional and used only for shared rate limiting.

```bash
cd infra
docker compose up --build
```

Endpoints:

- Web: `http://127.0.0.1:3100/login`
- MVP: `http://127.0.0.1:3100/app/projects/manufacturing-demo-project/mvp`
- API: `http://127.0.0.1:8100/health`

Start the optional shared rate limiter with:

```bash
docker compose --profile rate-limit up --build
```

Neo4j, background workers and prototype static-site deployment are not part of the current product infrastructure.
