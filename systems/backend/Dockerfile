FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

ARG GEN_DATA_SOURCE_REVISION=ec62592ccaa13990ddb1d3465f108ae6d9f0e566

WORKDIR /build

COPY ml /build/ml
COPY systems/backend /build/backend

# Pin production to one reviewed gen_data source revision. Only canonical
# source files and safe release evidence are extracted; model/prediction
# fixtures from gen_data are deliberately excluded from the runtime image.
RUN GEN_DATA_SOURCE_REVISION="${GEN_DATA_SOURCE_REVISION}" python - <<'PY'
import os
import shutil
import tarfile
import tempfile
import urllib.request
from pathlib import Path

revision = os.environ["GEN_DATA_SOURCE_REVISION"].strip()
if len(revision) != 40 or any(char not in "0123456789abcdef" for char in revision.lower()):
    raise SystemExit("GEN_DATA_SOURCE_REVISION must be a full Git commit SHA")
required = {
    "canonical/dataset/asset_master.csv",
    "canonical/dataset/asset_relation.csv",
    "canonical/dataset/compressor_sensor_observation.csv",
    "canonical/dataset/cnc_sensor_observation.csv",
    "canonical/dataset/cnc_production_cycle.csv",
    "canonical/dataset/maintenance_event.csv",
    "canonical/dataset/dataset_manifest.json",
    "canonical/validation/package_validation.json",
    "canonical/validation/agent_claims_example_evaluation.json",
}
destination = Path("/build/gen_data_source")
destination.mkdir(parents=True, exist_ok=True)
url = f"https://codeload.github.com/oosuhada/agentic-ontology-dashboard/tar.gz/{revision}"
with tempfile.NamedTemporaryFile(suffix=".tar.gz") as archive:
    with urllib.request.urlopen(url, timeout=120) as response:
        shutil.copyfileobj(response, archive)
    archive.flush()
    with tarfile.open(archive.name, "r:gz") as bundle:
        found = set()
        for member in bundle.getmembers():
            if not member.isfile():
                continue
            parts = Path(member.name).parts
            if len(parts) < 2:
                continue
            relative = Path(*parts[1:]).as_posix()
            if relative not in required:
                continue
            source = bundle.extractfile(member)
            if source is None:
                raise SystemExit(f"cannot read gen_data source member: {relative}")
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("wb") as handle:
                shutil.copyfileobj(source, handle)
            found.add(relative)
missing = sorted(required - found)
if missing:
    raise SystemExit(f"gen_data source revision is missing required files: {missing}")
(destination / ".source_revision").write_text(revision + "\n", encoding="utf-8")
PY

# Render demo deployments need PostgreSQL support even when the platform does
# not pass a Docker build arg. Local/CI Compose explicitly overrides this with
# API_EXTRAS when a smaller image is desired.
ARG API_EXTRAS="postgres,model-runtimes"
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir --prefix=/install /build/ml \
    && if [ -n "$API_EXTRAS" ]; then \
         python -m pip install --no-cache-dir --prefix=/install "/build/backend[$API_EXTRAS]"; \
       else \
         python -m pip install --no-cache-dir --prefix=/install /build/backend; \
       fi

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/home/ontology \
    TMPDIR=/tmp \
    ONTOLOGY_DASHBOARD_PROJECT_ROOT=/app \
    ONTOLOGY_DASHBOARD_MIGRATION_ROOT=/app/systems/backend/migrations

RUN apt-get update -qq \
    && apt-get install -y -qq --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 ontology \
    && useradd --uid 10001 --gid 10001 --create-home --shell /usr/sbin/nologin ontology

COPY --from=builder /install /usr/local
COPY --from=builder /build/gen_data_source /app/.source/gen_data

WORKDIR /app
COPY --chown=10001:10001 systems/__init__.py /app/systems/__init__.py
COPY --chown=10001:10001 systems/backend /app/systems/backend
COPY --chown=10001:10001 contracts/schemas /app/contracts/schemas
COPY --chown=10001:10001 prompts /app/prompts
COPY --chown=10001:10001 data/fixtures /app/data/fixtures

# Runtime state is written by the non-root API process. Create the writable
# roots before dropping privileges so local SQLite and object storage do not
# depend on root-owned /app directory permissions.
RUN mkdir -p /app/data/local /app/.runtime/object-storage \
    && chown -R 10001:10001 /app/data/local /app/.runtime

USER 10001

EXPOSE 8000

STOPSIGNAL SIGTERM
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-server-header"]
