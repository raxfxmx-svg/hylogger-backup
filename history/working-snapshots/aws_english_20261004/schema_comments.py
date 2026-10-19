"""English database descriptions; table definitions and privileges stay intact.
Use English database descriptions while preserving table definitions and permissions.
"""
COMMENTS = [
    "COMMENT ON COLUMN core.metric_definition.is_probability IS 'Source/canonical probability semantics: true, false, or NULL for unknown/inapplicable; Wt is explicitly false.'",
    "COMMENT ON COLUMN core.metric_definition.source_log_id IS 'Source log identifier for auxiliary metrics; keep separate source IDs when shared semantics are unconfirmed.'",
    "COMMENT ON CONSTRAINT asset_location_content_identity_fkey ON core.asset_location IS 'The declared copy hash must match the asset identity; no external API validation is required.'",
    "COMMENT ON TRIGGER validate_sample_relations ON core.scan_sample IS 'Validate tray, section, axis bounds, and interval positions for inserted samples; repeated depths are allowed.'",
    "COMMENT ON TABLE core.dataset_succession IS 'User-confirmed display succession and its evidence; this does not establish a physical branch trajectory.'",
    "COMMENT ON TABLE core.borehole_composite IS 'Per-release 3D borehole display composite; original datasets, images, and samples remain complete.'",
    "COMMENT ON TABLE core.borehole_composite_part IS '3D selection windows and inclusive source sample intervals; 2D reads full samples by axis_id without these selections.'",
    "COMMENT ON VIEW core.v_borehole_dataset_full IS '2D datasets share the measured-depth scale while retaining complete ranges and independent image relationships.'",
]


def apply_comments(conn):
    """Update description metadata without changing columns, constraints, or roles.
Update descriptions while preserving fields, constraints and roles.
    """
    for statement in COMMENTS:
        conn.execute(statement)
