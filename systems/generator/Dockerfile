FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    ONTOLOGY_DASHBOARD_PROJECT_ROOT=/app

WORKDIR /app

RUN apt-get update -qq \
    && apt-get install -y -qq --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY systems/generator/requirements.txt /tmp/generator-requirements.txt
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r /tmp/generator-requirements.txt

# Generator remains an independent deployment unit.
# Backend source is not copied. Only shared contract files required by
# Generator runtime validation are copied explicitly.
COPY systems/__init__.py /app/systems/__init__.py
COPY systems/generator /app/systems/generator

# Shared contracts consumed by Generator at runtime
COPY contracts/schemas /app/contracts/schemas

RUN groupadd --gid 10002 generator \
    && useradd --uid 10002 --gid 10002 --create-home --shell /usr/sbin/nologin generator \
    && mkdir -p /app/data /app/data_preprocessed /app/ontology /app/models_store /data/source /data/preprocessed /data/ontology /data/models /artifacts /logs \
    && chown -R 10002:10002 /app /data /artifacts /logs

USER 10002

ENTRYPOINT ["python", "-m", "systems.generator.entrypoint"]
CMD ["run"]
