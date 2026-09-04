CREATE TABLE IF NOT EXISTS ontology_interface_definitions (
  id text NOT NULL,
  version integer NOT NULL,
  organization_id text NOT NULL,
  project_id text NOT NULL,
  display_name text NOT NULL,
  status text NOT NULL,
  property_contract_json jsonb NOT NULL,
  capability_contract_json jsonb NOT NULL,
  created_by text NOT NULL,
  created_at timestamptz NOT NULL,
  PRIMARY KEY (organization_id, project_id, id, version)
);
CREATE TABLE IF NOT EXISTS ontology_interface_implementations (
  organization_id text NOT NULL, project_id text NOT NULL, interface_id text NOT NULL,
  interface_version integer NOT NULL, object_type_id text NOT NULL,
  property_mapping_json jsonb NOT NULL, created_at timestamptz NOT NULL,
  PRIMARY KEY (organization_id, project_id, interface_id, interface_version, object_type_id)
);
CREATE TABLE IF NOT EXISTS governed_action_definitions (
  id text NOT NULL, version integer NOT NULL, organization_id text NOT NULL,
  project_id text NOT NULL, display_name text NOT NULL, target_interface_id text NOT NULL,
  parameter_schema_json jsonb NOT NULL, execution_mode text NOT NULL,
  approval_required boolean NOT NULL DEFAULT false, required_permission text NOT NULL,
  status text NOT NULL, created_at timestamptz NOT NULL,
  PRIMARY KEY (organization_id, project_id, id, version)
);
CREATE TABLE IF NOT EXISTS governed_function_definitions (
  id text NOT NULL, version integer NOT NULL, organization_id text NOT NULL,
  project_id text NOT NULL, display_name text NOT NULL, input_schema_json jsonb NOT NULL,
  output_schema_json jsonb NOT NULL, runtime_checksum text NOT NULL, timeout_ms integer NOT NULL,
  network_policy text NOT NULL, status text NOT NULL, created_at timestamptz NOT NULL,
  PRIMARY KEY (organization_id, project_id, id, version)
);
CREATE TABLE IF NOT EXISTS governed_function_executions (
  id text PRIMARY KEY, organization_id text NOT NULL, project_id text NOT NULL,
  function_id text NOT NULL, function_version integer NOT NULL, input_json jsonb NOT NULL,
  output_json jsonb NOT NULL, state text NOT NULL, duration_ms integer NOT NULL,
  created_by text NOT NULL, created_at timestamptz NOT NULL
);

ALTER TABLE ontology_interface_definitions ENABLE ROW LEVEL SECURITY;
ALTER TABLE ontology_interface_implementations ENABLE ROW LEVEL SECURITY;
ALTER TABLE governed_action_definitions ENABLE ROW LEVEL SECURITY;
ALTER TABLE governed_function_definitions ENABLE ROW LEVEL SECURITY;
ALTER TABLE governed_function_executions ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS ontology_interface_definitions_tenant ON ontology_interface_definitions;
CREATE POLICY ontology_interface_definitions_tenant ON ontology_interface_definitions USING (
  organization_id = current_setting('app.organization_id', true)
  AND project_id = current_setting('app.project_id', true)
) WITH CHECK (
  organization_id = current_setting('app.organization_id', true)
  AND project_id = current_setting('app.project_id', true)
);
DROP POLICY IF EXISTS ontology_interface_implementations_tenant ON ontology_interface_implementations;
CREATE POLICY ontology_interface_implementations_tenant ON ontology_interface_implementations USING (
  organization_id = current_setting('app.organization_id', true)
  AND project_id = current_setting('app.project_id', true)
) WITH CHECK (
  organization_id = current_setting('app.organization_id', true)
  AND project_id = current_setting('app.project_id', true)
);
DROP POLICY IF EXISTS governed_action_definitions_tenant ON governed_action_definitions;
CREATE POLICY governed_action_definitions_tenant ON governed_action_definitions USING (
  organization_id = current_setting('app.organization_id', true)
  AND project_id = current_setting('app.project_id', true)
) WITH CHECK (
  organization_id = current_setting('app.organization_id', true)
  AND project_id = current_setting('app.project_id', true)
);
DROP POLICY IF EXISTS governed_function_definitions_tenant ON governed_function_definitions;
CREATE POLICY governed_function_definitions_tenant ON governed_function_definitions USING (
  organization_id = current_setting('app.organization_id', true)
  AND project_id = current_setting('app.project_id', true)
) WITH CHECK (
  organization_id = current_setting('app.organization_id', true)
  AND project_id = current_setting('app.project_id', true)
);
DROP POLICY IF EXISTS governed_function_executions_tenant ON governed_function_executions;
CREATE POLICY governed_function_executions_tenant ON governed_function_executions USING (
  organization_id = current_setting('app.organization_id', true)
  AND project_id = current_setting('app.project_id', true)
) WITH CHECK (
  organization_id = current_setting('app.organization_id', true)
  AND project_id = current_setting('app.project_id', true)
);
