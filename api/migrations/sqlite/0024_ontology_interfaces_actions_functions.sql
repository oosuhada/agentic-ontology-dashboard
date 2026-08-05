CREATE TABLE IF NOT EXISTS ontology_interface_definitions (
  id TEXT NOT NULL,
  version INTEGER NOT NULL,
  organization_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  display_name TEXT NOT NULL,
  status TEXT NOT NULL,
  property_contract_json TEXT NOT NULL,
  capability_contract_json TEXT NOT NULL,
  created_by TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (organization_id, project_id, id, version)
);

CREATE TABLE IF NOT EXISTS ontology_interface_implementations (
  organization_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  interface_id TEXT NOT NULL,
  interface_version INTEGER NOT NULL,
  object_type_id TEXT NOT NULL,
  property_mapping_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (organization_id, project_id, interface_id, interface_version, object_type_id)
);

CREATE TABLE IF NOT EXISTS governed_action_definitions (
  id TEXT NOT NULL,
  version INTEGER NOT NULL,
  organization_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  display_name TEXT NOT NULL,
  target_interface_id TEXT NOT NULL,
  parameter_schema_json TEXT NOT NULL,
  execution_mode TEXT NOT NULL,
  approval_required INTEGER NOT NULL DEFAULT 0,
  required_permission TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (organization_id, project_id, id, version)
);

CREATE TABLE IF NOT EXISTS governed_function_definitions (
  id TEXT NOT NULL,
  version INTEGER NOT NULL,
  organization_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  display_name TEXT NOT NULL,
  input_schema_json TEXT NOT NULL,
  output_schema_json TEXT NOT NULL,
  runtime_checksum TEXT NOT NULL,
  timeout_ms INTEGER NOT NULL,
  network_policy TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (organization_id, project_id, id, version)
);

CREATE TABLE IF NOT EXISTS governed_function_executions (
  id TEXT PRIMARY KEY,
  organization_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  function_id TEXT NOT NULL,
  function_version INTEGER NOT NULL,
  input_json TEXT NOT NULL,
  output_json TEXT NOT NULL,
  state TEXT NOT NULL,
  duration_ms INTEGER NOT NULL,
  created_by TEXT NOT NULL,
  created_at TEXT NOT NULL
);

