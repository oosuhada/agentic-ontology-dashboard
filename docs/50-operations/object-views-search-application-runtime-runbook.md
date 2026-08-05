# Object Views, Search and Application Runtime Runbook

Commercial V4 generates a standard Object View from Object Type and Interface
metadata, while allowing published configured views for full-page and panel form
factors. Missing configured views fall back to the standard view rather than a blank
screen.

Global search ranks exact, prefix and full-text matches after Project scope, type and
marking filters have been applied. Restricted resources never enter the returned
result set merely to be hidden by the browser.

The metadata application runtime accepts only versioned components from the catalog,
typed variables and typed event bindings. JavaScript expressions and arbitrary React
component names are not accepted.

```bash
.venv/bin/python -m pytest -q \
  tests/test_application_runtime_phase29.py \
  tests/test_persistence_foundation.py \
  tests/test_predictive_maintenance_postgresql.py

cd web
npm run lint
npm test -- --run src/platform/application/applicationRegistry.test.ts
npm run build
```

Open Commercial V4, select **Objects**, inspect generated views and the component
composition, then use Global search. The current deterministic index is a local
verification implementation; optional semantic ranking remains behind the typed
Project 3 boundary and is not represented as configured without that service.
