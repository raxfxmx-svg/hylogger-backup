# Connect the API to the Sydney pilot

Use this guide for the existing AWS deployment. The database has already been
restored. Do not run restore or migrations against `database-1 / etl4_core`.
The five-hole deployment and full live checks passed on 2026-09-18, recorded in
`validation/cloud_api_acceptance.json` and `validation/deployment_summary.json`.
The PostgreSQL reader exists. Contributor 3 should start with
[AWS CLI setup](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-quickstart.html), which records provisioning status
and the exact local authentication steps. Other recipients need their own approved
AWS identity with the runtime permissions described below.

## Target

| Setting | Value |
| --- | --- |
| AWS account / region | `000000000000` / `ap-southeast-2` |
| Aurora cluster | `database-1` (Aurora Express, PostgreSQL 17.9) |
| Host | `db.example.com` |
| Database / port | `etl4_core` / `5432` |
| Database login | `etl4_reader`, IAM authentication; no database password |
| TLS | `verify-full`, trusted public CA bundle |
| S3 bucket | `hyloggerdemo-000000000000-ap-southeast-2-an` |
| S3 prefix | `etl4/releases/fd02659c-dc3d-52ea-a8eb-c032b91e7624` |
| Logical storage root | `etl4_s3_primary` |
| Fixed data | 5 holes, 261,892 current samples, 2,810 external files |

This Aurora Express gateway uses public CA roots, not the ordinary RDS regional
certificate bundle. The launcher selects the system public CA bundle or certifi;
`ETL4_CA_FILE` can supply an approved public CA bundle explicitly.
[AWS Express connection documentation](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/CHAP_GettingStartedAurora.AuroraPostgreSQL.ExpressConfig.html).

## Access required from the AWS administrator

Use your own approved AWS profile or workload IAM role. The current project uses
an IAM user with `aws login` for TeamMemberA; IAM Identity Center/SSO is not enabled.
Browser login alone does not configure the local SDK. Do not request the database administrator's password
or copy the sender's AWS credentials. The runtime identity needs:

- `rds-db:connect` for the cluster resource ID and `etl4_reader` only.
- `s3:GetObject` on this exact release prefix. The API does not need S3 upload,
  delete or bucket-list permissions.
- If objects later use a customer-managed KMS key, the corresponding decrypt
  permission must be reviewed separately.

`runtime_policy.template.json` contains the scoped data permissions for the
administrator to assign. Keeping this file locally does not grant access.
It contains the verified cluster resource ID
`cluster-EXAMPLE`. Confirm it with this read-only command if
the target ever changes; it is not the name `database-1`:

```bash
aws rds describe-db-clusters --db-cluster-identifier database-1 --region ap-southeast-2 --query 'DBClusters[0].DbClusterResourceId' --output text
```

The administrator must assign the reviewed policy to the intended identity or
permission set. Creating the PostgreSQL reader alone does not grant a teammate
AWS access. A successful IAM token generation also does not prove connectivity.
[AWS IAM database policy documentation](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/UsingWithRDS.IAMDBAuth.IAMPolicy.html).

## Install and check

Run from the handoff folder containing the main `README.md`. Python 3.12 or 3.13
is suitable for the pinned cloud requirements; CloudShell used Python 3.13.

PowerShell:

```powershell
py -3.12 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r deployment/requirements-cloud.txt
$env:AWS_PROFILE = 'etl4-teammembera'  # Configure both profiles in TEAMMEMBERA_SIGN_IN.md first
aws login --profile etl4-teammembera-signin
& .\.venv\Scripts\python.exe deployment/run_api.py --check
```

Linux (using an already configured approved profile):

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r deployment/requirements-cloud.txt
export AWS_PROFILE=etl4-teammembera
aws login --profile etl4-teammembera-signin
python deployment/run_api.py --check
```

CloudShell is an operator alternative only: it uses the current console identity
and does not need `AWS_PROFILE`. TeamMemberA's scoped access does not include CloudShell.

The check uses live Aurora and S3 and verifies sample 15, its scalar value and
PNG. It makes no database or S3 writes. Success prints `LIVE_CHECK_PASSED`.
The cluster can pause after five idle minutes. The API permits 60 seconds for a
new database connection so that it can resume. The first request after an idle
period can therefore be slower; HTTP clients should allow more than 60 seconds
for that first check. [AWS auto-pause guidance](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-serverless-v2-auto-pause.html).
The broader operator acceptance is `python deployment/smoke_cloud.py`, covering
13 image fixtures and all eight spectral arrays against recorded golden values.

## Start the private API

```powershell
& .\.venv\Scripts\python.exe deployment/run_api.py
```

The launcher reads non-secret settings from `deployment/target.json`, uses
`etl4_reader` with fresh IAM tokens, and binds to `127.0.0.1:8000`. Enter a private
bearer token of at least 32 characters when prompted; input is hidden. You can
also supply it through your existing secret manager as `ETL4_API_TOKEN`. The
launcher does not print or save the token. This is a separate API token, not an
AWS IAM token or a database password.

In your HTTP client, set `Authorization: Bearer <the-token-you-entered>` and test:

| Request | Expected result |
| --- | --- |
| `GET /health` | Database reachable; this route alone does not verify S3 |
| `GET /v1/holes` | Five holes, 261,892 samples in total |
| `GET /v1/holes/07THD002/logs` | Available result and image logs |
| `GET /v1/holes/07THD002/samples/15?log_id=a4a5c7d3-0fe8-53be-97a2-02a5c7771ae8` | Depth `62.50175`, scalar `Muscovite`, image content path |
| `GET <images[0].content_path>` | Authenticated PNG, 399 by 25 pixels |

For detailed result and spectral semantics, see [the cloud API guide](../cloud_api/README.md)
and [the API contract](../docs/API_HANDOFF.md). Select samples by axis and
zero-based sample number; equal depth does not mean the same sample.

The data is read only for the API. S3 remains private. This package supplies the
pilot implementation and cloud data connection; it does not supply a persistent
public API URL, domain, HTTPS service or production user authentication. The API
team chooses its hosting environment separately. No EC2 instance was created
for the five-hole transfer.

## Resume an interrupted deployment (operator only)

The current control files are under `~/etl4-pilot` in Sydney CloudShell. Completed
uploads are retained even if the console session expires. Check the stored
validation reports before repeating a step. After reconnecting, activate the
existing `~/etl4-env` environment and use:

```bash
~/etl4-env/bin/python ~/etl4-pilot/deployment/cloud_runner.py verify-s3
~/etl4-env/bin/python ~/etl4-pilot/deployment/cloud_runner.py register-s3
~/etl4-env/bin/python ~/etl4-pilot/deployment/smoke_cloud.py
```

Run each step only after the preceding one succeeds. Registration refuses an
incomplete checksum receipt. `create-reader` is a one-time operation; inspect the
existing role before retrying it. Never rerun restore on the populated database.
Only after successful acceptance should the operator distribute the completed
reports with this package.
