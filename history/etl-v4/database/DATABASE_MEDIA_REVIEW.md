# Database and Media Findings

On 2026-09-09, I checked the five-borehole database and its media files, then reproduced invalid writes and concurrency cases in a restored test database. The published data matched its files; the tests identified gaps in publication sealing, crop provenance and replay behavior. The test database was removed, and the original database remained unchanged. These findings describe that historical version, before the later refactoring.

| Check | Result |
|---|---|
| Tables / foreign keys | 36 / 74; no unvalidated foreign keys or invalid indexes |
| Current release | 5 dataset revisions; 261,892 real samples |
| Retained history | 5 datasets, 10 revisions, 3 releases; 523,784 sample rows |
| Media | 249 tray images, 1,361 row PNGs, 8 spectral matrices, 448 blocks |
| Database size | 191,204,499 bytes |
| Unique referenced files | 2,810 paths; 2,400,546,756 bytes, verified by size and SHA256 |
| Sample-to-row mapping | Exactly one current row mapping per sample |
| Crop checks | All 1,361 source/crop pairs matched in pixels, dimensions and source identity |
| Structural checks | No violations in 21 queries; release manifests matched their relational members |

Current release: `fd02659c-dc3d-52ea-a8eb-c032b91e7624`. Per-hole sample counts were 05KCD001: 22,356; 07THD002: 116,424; 07THD003: 54,432; 09ATD015: 46,030; 09ATD019: 22,650. Database size includes history and allocated space; the database dump does not contain external media.

The restored-copy tests showed:

- Published revisions still accepted new logs, and a release could gain a sixth relational member while its immutable JSON manifest still listed five. UPDATE/DELETE protection did not seal the set of INSERTs.
- An empty, unvalidated release could become active. Step 29 also switched the pointer before writing the external manifest; this file-failure case was identified in code, not injected into the live database.
- A same-log crop from another tray, and an incorrect `flip_x=true` declaration, could pass existing checks. Cross-dataset frame links were correctly rejected. Actual published crops all matched.
- Sealed-package import still read mutable global `media_work` steps 22 and 27, making replay depend on the old workspace.
- Verification-code changes altered the package identity from `74ef7579...` to `2825b293...` and changed all five revision IDs. Step 20 also depended on the earlier five-revision release.
- Overlapping image regions were rejected under READ COMMITTED but both committed under REPEATABLE READ after concurrent transactions had taken their snapshots. Advisory locks alone did not refresh those snapshots.

These results motivated sealed revisions and controlled publication, explicit crop-source relationships, package-only imports, separate data-rule and verification versions, and concurrency-aware constraints. They were recommendations in this report, not fixes applied by this review.

Sample identity remains `(axis_id, sample_no)`, independently of repeated depth values. The approximate row indicator is `p=(sample_no-a)/(b-a)`, or 0.5 for one sample, with pixel position `p*(width_px-1)`; real depth comes from `scan_sample.md_m`. Weights are not calibrated probabilities, and missing survey angles remain missing. The three multi-dataset boreholes had not yet been imported in this snapshot.

The historical dictionary incorrectly described `borehole_revision.coordinate_basis` as image pixels; it means collar-coordinate provenance. Only `image_region.coordinate_basis` describes pixel coordinates. This documentation issue did not change database values.

See [the review script](30_audit_media_database.py), [recorded results](reports/30_media_database_audit.json), [schema dictionary](schema_dictionary.md) and [architecture](architecture.md).
