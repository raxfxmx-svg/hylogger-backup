# Connect the standalone API supplement

Run commands from the extracted folder containing the top-level README.
Use Python 3.12 or 3.13. The existing Aurora database and S3 objects are already
populated; no database restore, migration or ETL operation is needed.

## AWS access

The target is project account `000000000000`, region `ap-southeast-2`, database
`etl4_core`, using the existing `etl4_reader` PostgreSQL role. Configuration is
in `target.json`. The fixed release is
`fd02659c-dc3d-52ea-a8eb-c032b91e7624`: five holes and 261,892 current samples.

Your own AWS identity must be authorized to connect as `etl4_reader` and read
the fixed S3 release prefix. See `runtime_policy.template.json`. A local copy of
that policy does not grant access. Browser login alone is not an SDK login.

TeamMemberA: read [AWS CLI setup](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-quickstart.html) first. The recorded plan uses
an IAM user with CLI temporary credentials, not an SSO account. A console review
on 2026-09-23 confirmed that your account and required policies are configured;
your console last sign-in was 2026-09-22 15:17 (UTC+08:00).
Use your existing sign-in details and perform your own live check.
Do not use an administrator's credentials or register a personal root account.

## Install and check (PowerShell)

After completing the two AWS profile setup steps in TEAMMEMBERA_SIGN_IN.md:

```powershell
py -3.12 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r deployment/requirements-cloud.txt
& .\.venv\Scripts\python.exe verify_package.py
$env:AWS_PROFILE = 'etl4-teammembera'
aws login --profile etl4-teammembera-signin
aws sts get-caller-identity --profile etl4-teammembera
& .\.venv\Scripts\python.exe deployment/run_api.py --check
```

Expected identity: account `000000000000`, user `teammembera.Contributor3`.
An approved alternative identity can use its own profile instead.

The live check prints `LIVE_CHECK_PASSED` only after checking IAM/TLS database
access, sample 15, its Muscovite scalar and the corresponding private S3 PNG.
It does not write to the database or S3. It requires internet access and completed
AWS permissions. Aurora can take time to resume after inactivity; allow more than
60 seconds for a first request. A successful STS call alone is not a data check.

The launcher uses public certificate authorities for the Aurora Express gateway,
with `sslmode=verify-full`. It generates a fresh IAM database token per connection;
there is no PostgreSQL password to place in `target.json`.

## Start the local API

```powershell
& .\.venv\Scripts\python.exe deployment/run_api.py
```

Enter your own private API bearer token of at least 32 characters at the hidden
prompt. This is separate from the AWS console password and AWS session tokens.
Use `Authorization: Bearer <your-api-token>` for all requests, including images
and health. The service listens on `http://127.0.0.1:8000` on your computer.
The token can also be supplied through your existing secret handling as
`ETL4_API_TOKEN`; never commit it or put it in shared configuration files.

Read [the route guide](../cloud_api/README.md) for examples and limitations.
No public API address, HTTPS hosting, account-wide permissions, or CloudShell
access is included. The API team can adapt the code for its chosen hosting setup.

## Troubleshooting

- `ModuleNotFoundError`: install requirements in the same virtual environment used
  to run the launcher; keep both `deployment/` and `cloud_api/` in this folder.
- An unknown `aws login` command: install AWS CLI v2 version 2.32.0 or newer.
- Expired credentials: sign in again using the sign-in profile above.
- Wrong account: choose the project IAM identity in the browser and sign in again.
- AWS/SQL AccessDenied or failed live check: ask the administrator to confirm the
  identity policy and reader role. Do not repair this by restoring the database.
- S3 console or bucket-list AccessDenied: listing is outside the intended read
  permissions; use the supplied live check to test an actual permitted object.

Historical evidence under `validation/` records the operator's earlier successful
cloud checks. It is not evidence that the recipient's new credentials work today.
