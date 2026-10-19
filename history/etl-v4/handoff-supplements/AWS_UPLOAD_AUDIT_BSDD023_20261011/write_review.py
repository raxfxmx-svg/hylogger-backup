"""Write an English report from the read-only BSDD023 audit evidence."""
import json
from pathlib import Path
root=Path(__file__).resolve().parent
e=root/'evidence_verified'
a=json.loads((e/'audit_report.json').read_text())
s=json.loads((e/'stream_sha256_report.json').read_text())
l=json.loads((root/'local_scope_verification.json').read_text())
m=json.loads((e/'export/manifest.json').read_text())
native={v['key'] for v in a['objects'] if v.get('sha256_verified_by_s3')}
streamed={v['key'] for v in s['objects'] if v['passed']}
base=a['manifest_key'].rsplit('/',1)[0]
delivery={base+'/'+p for p in m['files']}|{a['manifest_key']}
assert len(native|streamed|delivery)==315
assert not a.get('fatal_error') and all(v['passed'] for v in a['checks'])
assert s['all_passed'] and not l['scope_issues'] and l['asset_table_matches_manifest']
report=f'''ETL4 UPLOAD REVIEW - BSDD023
Date: 11 October 2026 (Asia/Shanghai)
Result: upload verified; ready for owner review before cloud import/publication.

SCOPE AND AUTHORIZATION
The user reported one further teammate upload but did not know its hole/batch ID.
This review targets the newest single-borehole manifest found in S3: BSDD023,
uploaded at 2026-10-11 10:40:20 +08:00. Other recent uploads contain multiple holes.
The uploader's identity was not established from S3 LastModified. Confirm this
batch ID with the teammate when collecting the original upload receipt.
Only a read-only review was requested and performed. No merge or publication.

BATCH AND DESTINATION
Batch ID: {a['batch_id']}
Manifest SHA256: {a['manifest_sha256']}
Borehole: BSDD023
Borehole UUID: {a['datasets'][0]['borehole_id']}
Dataset UUID: {a['datasets'][0]['dataset_id']}
Revision UUID: {a['datasets'][0]['dataset_revision_id']}
Source dataset ID: {a['datasets'][0]['source_dataset_id']}
AWS account: 000000000000
Region: ap-southeast-2 (Sydney)
Database: etl4_core
S3 bucket: {a['bucket']}
Manifest key: {a['manifest_key']}

VERIFIED RESULTS
- All 315 expected S3 objects exist and match their declared sizes.
- 275 distinct asset objects, 39 delivery files, and one manifest.
- 289 database asset records reference the 275 distinct asset objects.
- Total referenced size: 73,747,464 bytes (73.75 MB / 70.33 MiB).
  This is referenced batch size, not a measurement of newly stored bytes.
- All 315 SHA256 identities checked: eight native S3 FULL_OBJECT SHA256,
  267 asset bodies streamed and hashed, and 40 delivery files downloaded/hashed.
- No bulk image/spectrum download to the owner's computer was needed.
- Manifest identity, file paths and schema scope passed the owner's validator.
- Both delivered local acceptance stages passed and match this revision.
- All 29 structured table files passed SHA256, row counts, column scope, and
  primary-key uniqueness checks: 9,314 total table rows.
- Asset table entries exactly match the manifest's asset identities.
- Revision, borehole, sample-axis and spectral-array references checked against
  the declared batch scope; no out-of-scope references found in these checks.
- All six migrations match both owner code and the live cloud migration list.
  Columns, types and primary keys match the live cloud schema.

DATA CONTENT
One borehole; one dataset.
8,040 samples; observed depth range 0.0052-51.39814 m.
99 logs and 160 structured data chunks in the delivered acceptance evidence.
15 original image frames; 60 image regions and 60 cropped core-row images.
Two spectral arrays, each covering 8,040 samples (531 and 341 channels).
Both array layouts are verified_sample_major; both sample bindings are verified.
The delivered acceptance reports 20 official reference-spectrum comparisons.
Image mapping status is metadata_associated; this is not a claim of independently
surveyed pixel-to-depth precision.

QUALITY RECORDS
There are 16 informational duplicate-log-name preservation records and five
warning records: coordinate declarations differ (1), unresolved source reference
(1), and earlier spectral layout/binding warnings (3). The later spectral-array
and sample-map records are verified; the earlier warnings are preserved history.
Acceptance passed with the recorded limitations. This review did not independently
recompute scientific measurements or resolve source metadata discrepancies.

LIVE DATABASE FINDINGS (AT AUDIT TIME)
Active release: {a['cloud_active']['release_id']}
Active release switched: {a['cloud_active']['switched_at']}
Current release: 386 distinct boreholes, 391 datasets.
No matching BSDD023 borehole, incoming dataset, or revision is present in core.
No cloud import record exists for this batch.
The latest staged candidate matches the active release; no additional pending
candidate members were found at the time of the query.
Adding only this batch to that active release would give 387 boreholes and
392 datasets. Re-read the active release immediately before any later publication;
other owner-approved imports may change these totals.

NEXT STEPS BEFORE IMPORT/PUBLICATION
1. Obtain the teammate's original Step 39 upload_receipt.json. It is normally
   written locally and is not automatically uploaded with the manifest. No
   receipt was present in this S3 batch directory; no data re-upload is needed.
2. Match its batch ID, manifest SHA256, bucket, region, prefix and every object
   against this audit. Do not fabricate a Step 39 receipt from the audit output.
3. Obtain owner approval to merge and publish this new borehole.
4. Use the owner's controlled Step 40 workflow. The selected release must equal
   the current approved members plus this accepted dataset only. Recheck that
   the script's latest-candidate accumulation cannot include unrelated changes.
5. Verify the new borehole through the actual API after publication and confirm
   existing data remains readable. No live API request was performed in this audit.

LIMITATIONS AND CHANGE RECORD
S3 data objects, database business rows, active_release and IAM were unchanged.
Database reads used a read-only repeatable-read transaction. Small audit scripts
and evidence copies were stored in CloudShell and the local audit folder.
This is not a completed Step 40 import or a live API acceptance test.
The original receipt and definitive teammate attribution remain outstanding.

EVIDENCE
evidence_verified/audit_report.json
evidence_verified/stream_sha256_report.json
evidence_verified/export/manifest.json
local_scope_verification.json
Cloud archive SHA256:
973d660704f73008bc3b293fd6cdd1c42875c63a4cb9134075ef5781c8ffce36
'''
(root/'UPLOAD_REVIEW_EN.txt').write_text(report,encoding='utf-8')
reply=f'''I checked the newest single-borehole upload, BSDD023.

Batch ID: {a['batch_id']}

All 315 S3 objects are present and their SHA256 identities have been verified.
Both delivered acceptance stages pass, and the schema matches the cloud database.
This is a new borehole/dataset, with no matching cloud record or prior batch import.
It contains 8,040 samples, 15 original image frames, 60 cropped images and two
verified spectral arrays.

Please confirm that this is your latest upload and send the completed Step 39
upload_receipt.json. The manifest is already available from S3; no re-upload is
needed. Cloud merge/publication has not been performed and remains subject to
the owner's approval.
'''
(root/'TEAMMATE_REPLY_EN.txt').write_text(reply,encoding='utf-8')
print(json.dumps({'report':str(root/'UPLOAD_REVIEW_EN.txt'),'verified_objects':315,'status':'READY_FOR_OWNER_REVIEW; original upload receipt required before Step 40'}))
