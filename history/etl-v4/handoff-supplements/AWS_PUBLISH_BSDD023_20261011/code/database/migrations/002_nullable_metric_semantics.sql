-- The prepared dictionary uses NULL when probability semantics are not applicable
-- or not confirmed. A missing declaration must not be coerced into false.
ALTER TABLE core.metric_definition ALTER COLUMN is_probability DROP NOT NULL;
COMMENT ON COLUMN core.metric_definition.is_probability IS 'Probability semantics from the source/canonical dictionary: true, false, or NULL for unknown/inapplicable values; Wt is explicitly false.';
