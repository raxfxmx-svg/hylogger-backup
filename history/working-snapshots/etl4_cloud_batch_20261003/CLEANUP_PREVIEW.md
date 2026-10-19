# Cleanup Preview After the Twelve-Hole Delivery

No files were deleted. The preview listed 6,662 candidates totaling 1,595,121,029 bytes (1.486 GiB): refactor_work contained 5,652 files / 1,435,799,599 bytes; new_input_check 872 / 155,185,051; structure_input_20260930 138 / 4,136,379. All three had zero blockers within the checked scope. This was not confirmed reclaimable space.

See cleanup_file_list.txt and the per-workspace JSON previews for hashes, identities and retention reasons. The reference check covered registered new-format batches under the export root; it did not inspect old database asset_location references, older media releases or unregistered preparation directories. Deleting candidates could therefore break older local file reads. Raw data, evidence, reports, exports, databases and backups remained. Cloud objects were already delivered separately.
