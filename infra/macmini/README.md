# Mac mini production stack

This stack runs Frontend, Backend, PostgreSQL and the batch Generator on the Mac
mini. Vercel remains available for CI/preview validation; Render and Neon remain
untouched rollback sources during the validation period.

## Services and boundary

- `postgres`: PostgreSQL 18 + pgvector on the private Compose network only. The
  host bind mount targets `/var/lib/postgresql` (the PostgreSQL 18+ image
  layout), not the pre-18 `/var/lib/postgresql/data` path.
- `redis`: private-network-only ephemeral Redis used by the Backend's
  distributed production rate limiter. It exposes no host port and contains no
  authoritative application data.
- `backend`: canonical `systems/backend`, published only to `127.0.0.1:8110` for
  Cloudflare Tunnel. It reads `/artifacts/.../current` read-only via
  `MODEL_ARTIFACT_URI`.
- `generator`: one-shot batch profile. It owns extraction, ontology mapping,
  feature/label processing and immutable Model Artifact publication. It is not a
  continuously spinning API server.
- `frontend`: canonical `systems/frontend` nginx runtime, published only to
  `127.0.0.1:8120`. It builds with an empty `VITE_API_BASE_URL`, so browser API
  requests remain same-origin and nginx proxies `/api/*` to Backend through the
  private Compose alias `api:8000`.
- Vercel is retained as CI/preview validation rather than the production origin.

The production `.env` is server-only, mode `0600`, and must never be committed.

## Persistent layout

`ONTOLOGY_DATA_ROOT` contains `postgres/`, `generator/{source,data_preprocessed,ontology,models_store,logs}`,
`artifacts/`, `runtime-pipeline-input/`, and `backups/{neon,postgres,generator}`. Generated feature caches
can be recreated. PostgreSQL dumps, immutable Model Artifacts, mapping metadata,
and the source snapshot metadata are backup-worthy.

`GEN_DATA_RUNTIME_OUTPUT_ROOT` remains producer-owned and read-only to the
live-ingestor. The live-ingestor writes immutable, content-addressed Runtime
Prediction inputs only to `RUNTIME_PIPELINE_INPUT_ROOT`; Generator mounts that
same host directory at `/runtime-pipeline-input` read-only.

Create `RUNTIME_PIPELINE_INPUT_ROOT` with permissions that allow the
`live-ingestor` container to write and the Generator runtime to read. Set
`ONTOLOGY_DASHBOARD_GENERATOR_RUNTIME_ENQUEUE_URL` only when the persistent
Generator Runtime API is deployed; an Overlay event fails closed while that
endpoint is absent or unreachable.

## Startup / shutdown / logs

```sh
docker compose --env-file .env -f docker-compose.yml up -d postgres redis backend frontend
docker compose --env-file .env -f docker-compose.yml ps
docker compose --env-file .env -f docker-compose.yml logs -f frontend backend
docker compose --env-file .env -f docker-compose.yml stop frontend backend redis postgres
```

Do not publish port 5432. Cloudflare routes the product hostname only to the
frontend localhost port and may keep the dedicated Backend health/API hostname
on its backend localhost port. `restart: unless-stopped` makes the long-running
services return after OrbStack/host restart.

## Generator

The source contract is file/artifact based; there is no Python import from
`Biz-CollabCraft/gen_data`. Place or synchronize the pinned Canonical V3.1 CNC
and compressor telemetry/failure-truth files under `generator/source`. Both
trained families derive per-asset first-seven-day running baselines plus temporal
1 h / 6 h change and rolling statistics. Each immutable artifact embeds those
baseline statistics and a rolling-context contract so Backend can reproduce the
same 40 features from the current observation plus the preceding 35 ten-minute
observations without importing Generator or `gen_data` code.

```sh
./scripts/run-generator.sh
docker compose --env-file .env -f docker-compose.yml --profile generator run --rm generator llm-smoke
```

The complete run writes intermediate feature/label outputs to persistent
storage and publishes an immutable `model-artifact-v1.0`. `current` is an
operational alias only; the artifact version directories are never overwritten.
Promotion is blocked unless regression-sanity average precision is above label
prevalence and both regression/deployment evaluations detect positive rows.
Threshold selection is validation-only rather than a fixed 0.5 or test-set
optimization. Default tree-model parallelism is two workers. Weekly Sunday
03:15 local time is the provided retraining schedule, intentionally not every
sensor event.

On the 16 GiB / 8-core Mac mini, Compose caps PostgreSQL at 1.5 CPU / 2 GiB,
Redis at 0.25 CPU / 128 MiB, Backend at 2 CPU / 2 GiB, and Generator at 2 CPU /
4 GiB. Frontend is capped at 0.5 CPU / 256 MiB, so the stack cannot consume the
whole host alongside existing services.

### Optional Generator LLM provider

The ML path does not require an LLM. Extraction profiling and ontology mapping
can use an LLM and safely fall back to deterministic rules when credentials are
absent. Supported providers are:

- `GENERATOR_LLM_PROVIDER=openai` with `OPENAI_API_KEY`.
- `GENERATOR_LLM_PROVIDER=vertex_ai` with Google Vertex AI. Mac mini production
  uses project `flai-oosuhada-20260506`, location `global`, and
  `gemini-3.7-flash`. The server-side service-account JSON is mounted read-only
  through `GENERATOR_GOOGLE_APPLICATION_CREDENTIALS_HOST` and exposed inside
  the Generator container only as `GOOGLE_APPLICATION_CREDENTIALS`. A supported
  `VERTEX_AI_API_KEY` remains available as an alternative, but is not the
  production credential path.

Do not commit either provider's credential. The production service account is
expected to have only the Vertex AI runtime role needed by Generator.

The standalone image declares dependencies from the current Generator import
graph. Legacy `lightgbm`/`xgboost` declarations are intentionally not installed
because the merged canonical runtime does not import them; the production model
uses scikit-learn RandomForest with bounded worker count.

## Live `gen_data` → model → product loop

The weekly `generator` job trains and promotes Model Artifacts; it is not the
sensor stream. Production live data is a separate loop:

1. the `Biz-CollabCraft/gen_data` daemon runs under launchd and appends one
   complete 100-asset sensor tick every 10 wall-clock minutes by default;
2. `live-ingestor` watches those JSONL streams and publishes them into a
   separate `gen-data-wall-clock-live-v2` Dataset Version;
3. Backend diagnosis invokes the currently promoted CNC and compressor Model
   Artifacts and atomically refreshes the 100 current Result Artifacts;
4. the Operations frontend refreshes its governed runtime view every 30 seconds.

The immutable Canonical V3.1 Dataset Version remains the training/regression
baseline and is never appended to by the live loop. Production uses
`GEN_DATA_CLOCK_MODE=wall_clock`; `GEN_DATA_SPEED` remains an accelerated
simulation/replay setting and is not a substitute for physical wall-clock
semantics.

The wall-clock daemon aligns observations to absolute UTC cadence boundaries
(`:00`, `:10`, `:20`, ... for the current ten-minute contract). A restart does
not fabricate observations for downtime and does not reuse a legacy accelerated
watermark. The prior `gen-data-live-v1` Dataset Version and its output directory
remain immutable historical simulation lineage. Cutover therefore points both
the daemon and `live-ingestor` at a fresh runtime/output directory rather than
mixing the old future-dated stream into the new timeline.

The promoted temporal models currently require 35 prior ten-minute rows. A new
wall-clock Dataset Version therefore cannot produce a fresh inference immediately.
At creation time Backend uses the latest **non-future** pre-cutover observation and
its 35-row history to evaluate the current Model Artifact once for each of the 100
assets. Those seed results are stored in the new read model with explicit
`cutover_carry_forward` lineage. Pre-cutover rows are never copied into the new
wall-clock observation tables. Each asset is replaced by a real wall-clock
inference only after its new same-Dataset-Version history satisfies the Model
Artifact cadence/history contract.
Runtime Overlay remains stricter: its post-maintenance branch uses only that
branch's post-maintenance observations and never mixes pre-maintenance history.

After the production `.env` is configured, install/reload the source daemon and
start the ingestor with:

```bash
infra/macmini/scripts/install-live-runtime.sh
docker compose --env-file infra/macmini/.env -f infra/macmini/docker-compose.yml up -d live-ingestor
```

## PostgreSQL migration, backup, restore

Neon is dumped in PostgreSQL custom format with `--no-owner --no-acl`, retained
under `backups/neon`, then restored into the local PostgreSQL 18 service. Verify
schema migrations, row counts, indexes, foreign keys, representative queries,
and Backend API responses before cutover.

Daily local dumps use `scripts/postgres-backup.sh` and keep seven daily copies
plus four Sunday weekly snapshots.
Run `scripts/postgres-restore-test.sh <dump>` to restore into a temporary DB and
prove the dump is usable. `scripts/install-backup-schedules.sh` installs the
02:30 daily PostgreSQL backup and Sunday 04:30 Generator/artifact backup as
macOS LaunchAgents. `generator-backup.sh` stores immutable artifacts and mapping/
plan metadata while intentionally excluding reproducible feature matrices.

## Cloudflare production and Vercel CI/preview

Reuse the existing named Mac mini tunnel. The canonical production routes are:

```yaml
- hostname: ontology-api.oosu.dev
  service: http://127.0.0.1:8110
- hostname: ontology.oosu.dev
  service: http://127.0.0.1:8120
```

Validate the tunnel configuration before restarting it. Never commit tunnel
credentials. The single-label `ontology-api.oosu.dev` hostname is used because
the zone's standard `*.oosu.dev` certificate does not cover a two-label hostname
such as `api.ontology.oosu.dev`. The Mac mini frontend keeps browser requests
same-origin and proxies `/api/*` privately. Vercel may still rewrite `/api/*` to
`https://ontology-api.oosu.dev/api/*` for preview/CI deployments, but it is not
the canonical production origin.

## Rollback

### Guarantee boundary

The retained Vercel → Render → Neon stack is a **pre-cutover rollback path**,
not a post-cutover disaster-recovery/failover replica.

- Frontend rollback returns the Cloudflare `ontology.oosu.dev` catch-all to the
  retained Vercel production origin. The retained pre-cutover frontend route
  sends `/api/*` to Render.
- Application/database rollback uses the retained Render service with its
  existing `ONTOLOGY_DASHBOARD_DATABASE_URL` pointing to Neon. Do not repoint
  the Mac mini Backend to Neon over the public internet.
- Neon is the authoritative **pre-cutover** fallback state. Mac mini PostgreSQL
  does not continuously replicate post-cutover writes to Neon.
- The daily PostgreSQL dumps described above are local Mac mini recovery
  artifacts. They do not protect against total loss of the Mac mini and its
  local data root because no independent off-host copy is currently part of
  this PR.

Consequently, if the Mac mini and its storage are unavailable, the cloud
rollback RPO is the retained Neon cutover point: all writes accepted only by Mac
mini after that point may be lost from the fallback view. There is no guaranteed
RTO; changing Cloudflare ingress is manual and a retained Render instance may
need to cold-start. A post-cutover DR/failover claim requires a separate
off-host/replicated backup design, an explicit RPO/RTO, and a restore/failover
drill.

### Cloud rollback procedure

Before changing public ingress during an incident:

1. Check the retained Render `/health/ready` endpoint directly. The database and
   migration dependencies must report `ready`; optional demo Redis may remain
   unconfigured.
2. Check the retained Vercel production URL directly. Confirm `/` returns 200,
   unauthenticated `/api/projects` returns the expected 401, then use an approved
   demo/operator account to prove login, `/api/projects`, and at least one
   representative runtime API.
3. Record the current Mac mini and fallback Dataset Version/model identifiers and
   the latest accepted PostgreSQL backup or cutover timestamp. This makes the
   expected data-loss window explicit before traffic is moved.
4. Restore the last known-good pre-cutover Cloudflare ingress entry for
   `ontology.oosu.dev`, validate the tunnel configuration, and reload the tunnel.
5. Repeat the login and representative API smoke through
   `https://ontology.oosu.dev`. Record status codes and the fallback Dataset
   Version/model identifiers in the incident log.

Do not describe the rollback as zero-data-loss or as automatic failover unless
continuous replication/off-host recovery has been added and separately proven.

### 2026-08-19 cloud fallback smoke record

At `2026-08-19 12:51 KST`, the retained cloud path was checked directly from a
machine outside the Mac mini data plane, without changing Cloudflare production
ingress:

- Vercel production root: HTTP 200.
- Vercel `/api/projects` without a session: expected HTTP 401.
- Render `/health/ready`: HTTP 200 after cold-start delay; database=`ready`,
  migrations=`ready`. Earlier 25-second probes timed out while the retained
  service was cold, so rollback RTO must not assume an already-warm Render
  instance.
- Login through Vercel: HTTP 200; authenticated `/api/projects`: HTTP 200 with
  three projects.
- Manufacturing predictive-maintenance runtime context through Vercel: HTTP
  200, `relational_status=ready`, fallback Dataset Version
  `dsv-c42ef81d-f744-5b9b-8390-ac2e45bb8f17`, model version
  `compressor-signal-heuristic-v1, fixture-heuristic-v1`.
- At the same time the active Mac mini path reported Dataset Version
  `dsv-3a047e0d-b120-508a-99b2-e27d8e4cb213` and model version
  `cnc-random-forest-v3-f898a33ade7f, compressor-random-forest-v3-138e75c0f721`.
  The differing runtime lineage is concrete evidence that the cloud standby is
  a retained pre-cutover state rather than a synchronized post-cutover replica.

This smoke proves the direct Vercel → Render → Neon fallback data path was
reachable and could authenticate/read application data at that time. It does
**not** prove the Cloudflare ingress switch itself, an actual powered-off Mac
mini drill, post-cutover data parity, or post-cutover disaster recovery. Those
remain separate operational proofs.

## Secret handling

`POSTGRES_PASSWORD`, Neon URLs, `OPENAI_API_KEY`, `VERTEX_AI_API_KEY`, Render/Vercel/Cloudflare
credentials, and session/JWT secrets are never repository values. Store them in
the Mac mini `.env`/existing platform secret stores only, with permission 0600.
