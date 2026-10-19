ALTER TABLE core.metric_definition ADD COLUMN source_log_id text;
COMMENT ON COLUMN core.metric_definition.source_log_id IS 'Source log identity in the auxiliary metric dictionary; register each source ID separately when general semantics are unconfirmed.';
