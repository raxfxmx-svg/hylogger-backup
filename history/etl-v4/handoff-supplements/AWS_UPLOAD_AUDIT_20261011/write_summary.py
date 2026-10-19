"""Create the English owner/teammate report from verified audit evidence."""
import collections,gzip,hashlib,json
from pathlib import Path
root=Path(__file__).resolve().parent
e=root/'evidence_final'
a=json.loads((e/'audit_report.json').read_text())
s=json.loads((e/'stream_sha256_report.json').read_text())
c=json.loads((e/'revision_comparison.json').read_text())
new=[json.loads(x) for x in gzip.open(e/'export/tables/asset.jsonl.gz','rt')]
old=c['published_assets']
groups=[]
for group in sorted(set((x['asset_kind'],x['representation']) for x in old+new)):
    o=[x for x in old if (x['asset_kind'],x['representation'])==group]
    n=[x for x in new if (x['asset_kind'],x['representation'])==group]
    equal=sum((collections.Counter((x['sha256'],x['byte_size']) for x in o)&collections.Counter((x['sha256'],x['byte_size']) for x in n)).values())
    groups.append({'kind':group[0],'representation':group[1],'published':len(o),'incoming':len(n),'byte_identical_count':equal})
(root/'asset_content_comparison.json').write_text(json.dumps(groups,indent=2)+'\n')
native={x['key'] for x in a['objects'] if x.get('sha256_verified_by_s3')}
streamed={x['key'] for x in s['objects'] if x['passed']}
delivery={a['manifest_key'].rsplit('/',1)[0]+'/'+k for k in json.loads((e/'export/manifest.json').read_text())['files']}|{a['manifest_key']}
assert len(native|streamed|delivery)==848
assert s['all_passed'] and not a.get('fatal_error')
assert len(native)==634 and len(streamed)==174 and len(delivery)==40
text=f'''ETL4 UPLOAD REVIEW - 12DHDD0002
Reviewed: 11 October 2026 (Asia/Shanghai)

DECISION
The submitted S3 batch is complete and internally consistent. It is a new
revision of an already-published borehole/dataset, not an additional borehole.
No cloud merge or publication was performed. Keep the current published revision
unless the owner explicitly approves a reviewed replacement.

IDENTITY
AWS account: 000000000000
Region: ap-southeast-2 (Sydney)
Database: etl4_core
Bucket: {a['bucket']}
Batch: {a['batch_id']}
Manifest SHA256: {a['manifest_sha256']}
Manifest key: {a['manifest_key']}
Manifest completed upload: 2026-10-11 01:01:55 +08:00
Borehole: 12DHDD0002
Dataset: {c['incoming_revision']['dataset_id']}
Published revision: {c['published_revision']['id']}
Incoming revision: {c['incoming_revision']['id']}

UPLOAD VERIFICATION
- 848/848 expected objects exist, with the expected byte sizes.
- 808 distinct content-addressed asset objects, 39 delivery files, one manifest.
- 822 asset records reference the 808 distinct asset objects.
- Total referenced size: 623,199,591 bytes (623.20 MB / 594.33 MiB).
  This is the batch's referenced size, not proof that every byte was newly stored;
  Step 39 can reuse objects already present in the content-addressed store.
- All 848 SHA256 identities verified: 634 using native S3 FULL_OBJECT SHA256,
  174 asset bodies streamed and hashed in CloudShell, and 40 delivery files
  including the manifest downloaded and hashed. Asset bodies were not saved
  to the owner's computer.
- AES256 encryption reported for all 848 objects.
- Owner's export validator and Step 40 local-acceptance validator passed.
- Both delivered acceptance stages are passed and match the submitted revision.
- All 29 table files passed SHA256, row count, column, and primary-key checks.
- Six migrations and the complete column/type/key schema match owner code and
  the live cloud database. No migration is required for this submitted schema.

LIVE CLOUD STATE
Active release: {a['cloud_active']['release_id']}
Published: 2026-10-10 08:45:36 UTC
Current scope: 247 distinct boreholes, 252 datasets.
12DHDD0002 and this same dataset already belong to the active release.
The incoming revision is not in the database and this batch has no ingest_run.
Selecting the incoming revision would replace this dataset's published revision;
it would not increase the 247-hole / 252-dataset counts.
Latest staged candidate equals the active release; no unrelated candidate delta
was observed at the time of this check. Recheck immediately before any merge.

NEW VERSUS PUBLISHED DATA
- 238 raw files in each version: 230 have identical size/SHA256, eight differ.
- All 136 raw scalar assets, two raw spectral assets, one raw profile asset,
  and 84 original image assets have identical byte content.
- All 410 cropped core-row images have identical byte content, despite changed
  revision-dependent logical paths.
- All 1,906 structured data chunks have matching logical content digests and
  row coverage. This compares recorded logical digests; it is not a new
  independent scientific recomputation of the cloud-published values.
- Both versions have 55,310 samples, depth 51.30313-402.49927 m, 156 logs,
  84 image frames, 410 image regions, and two spectral arrays.
- Raw files that differ: datasets.json, download-report.txt,
  images_manifest.json, logs_image.json, logs_scalar.json,
  mosaics/e9a2c6bd-0628-44e4-aa26-b613465007a_Mosaic.html,
  package_manifest.json, scalar_manifest.json.
- Download timestamps, source snapshot, preparation/media fingerprints,
  pipeline fingerprint, revision ID and input digest differ. Binary canonical
  scalar/profile/axis files also differ; their checked data-chunk logical
  content is unchanged.
- Published assets: 928; incoming assets: 822. The count reduction is in
  media-evidence assets (132 versus 26), not missing image regions or crops.
  Evidence packaging should be reviewed if a replacement is later proposed.
- The incoming spectral arrays are verified_sample_major; sample mappings
  are verified. Earlier pipeline warning records remain in quality_issue and
  should not be misread as overriding these later verified statuses.

RECOMMENDED NEXT ACTION
Treat this as a successful local-processing and S3-upload test. Do not publish
it as a new borehole. Keep the existing published revision and allocate an
unpublished borehole for the next end-to-end import/publication test.
Ask the teammate for upload_receipt.json for the audit trail. The manifest and
delivery files were retrieved directly from S3, so no asset re-upload is needed.
Step 39 normally writes the receipt locally; it does not upload it automatically.
If replacement is intentional, review the processing/evidence differences first,
obtain the owner's explicit replacement decision, then validate the original
receipt against this exact batch/manifest/target before running Step 40.

LIMITS
All database work used read-only transactions. No database rows, release pointer,
S3 data objects, or IAM permissions were changed. Audit scripts and small evidence
copies were saved in the owner's CloudShell workspace and local audit folder.
Uploader identity was not inferred from LastModified; CloudTrail attribution was
not required to establish that this exact batch is present.
Scientific ETL stages were not recomputed. The original teammate receipt has not
been supplied. No live teammate API HTTP endpoint was tested.
Full Step 40 import/finalization acceptance has not been exercised for this batch.

EVIDENCE
evidence_final/audit_report.json
evidence_final/stream_sha256_report.json
evidence_final/revision_comparison.json
evidence_final/export/manifest.json
asset_content_comparison.json
Cloud audit archive SHA256:
4de442b086ef0c0f71b24d6e8e09d402e7eda79c58ff1d8d7b2650967c161409

The initial audit's failed "incoming ... are new to cloud" check is an expected
scope finding (existing dataset), not an upload-integrity failure. Timestamp
strings in revision_comparison can use a space versus T for the same instant;
source_created_at/source_modified_at are not substantive differences here.
'''
(root/'UPLOAD_REVIEW_EN.txt').write_text(text,encoding='utf-8')
reply='''The upload has been independently verified: all 848 objects are present and their SHA256 identities match, and both supplied acceptance stages pass.

However, 12DHDD0002 and this dataset are already in the active cloud release, which currently contains 247 boreholes and 252 datasets. Your batch has a different revision ID, but its raw scalar/spectral data, original images, 410 cropped images, and the 1,906 checked logical data chunks match the published version. It is not an additional borehole.

No merge or publication has been performed. My recommendation is to retain the current published revision and use an unpublished borehole for the next import/publication test. Please send the completed upload_receipt.json for the audit trail; the manifest has already been retrieved from S3, and no data re-upload is needed.
'''
(root/'TEAMMATE_REPLY_EN.txt').write_text(reply,encoding='utf-8')
print(json.dumps({'report':str(root/'UPLOAD_REVIEW_EN.txt'),'all_sha256_verified_objects':len(native|streamed|delivery),'recommended_action':'keep_current_release; retain uploaded batch for review'}))
