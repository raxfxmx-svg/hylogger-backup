"""Private pilot API. Start with uvicorn cloud_api.app:create_app --factory."""
from contextlib import contextmanager
from dataclasses import dataclass, field
import hmac
import os
from uuid import UUID

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row
from fastapi import FastAPI, Query, Path
from fastapi.responses import JSONResponse, Response
from .reader import RELEASE, HOLES, context, logs, read_sample
from .storage import APIError, S3Store, require


@dataclass(frozen=True)
class Settings:
    dsn: str = field(repr=False)
    token: str = field(repr=False)
    bucket: str
    region: str
    root_key: str = 'etl4_s3_primary'
    prefix: str = 'data'
    db_auth: str = 'password'

    @classmethod
    def from_env(cls):
        try:
            settings = cls(os.environ['ETL4_READ_DSN'], os.environ['ETL4_API_TOKEN'],
                os.environ['S3_BUCKET'], os.environ['AWS_REGION'],
                os.environ.get('ETL4_S3_ROOT_KEY', 'etl4_s3_primary'),
                os.environ.get('S3_PREFIX', 'data'), os.environ.get('ETL4_DB_AUTH', 'password'))
            params = conninfo_to_dict(settings.dsn)
            if (len(settings.token) < 32 or not settings.bucket or not settings.region
                    or settings.db_auth not in ('password', 'iam')
                    or params.get('sslmode') != 'verify-full' or not params.get('sslrootcert')
                    or not all(params.get(k) for k in ('host', 'user', 'dbname'))
                    or (settings.db_auth == 'iam' and 'password' in params)):
                raise ValueError()
            return settings
        except Exception:
            raise RuntimeError('Invalid cloud API configuration. See cloud_api/README.md; credentials were not printed.') from None


@contextmanager
def database(settings):
    options = conninfo_to_dict(settings.dsn)
    if settings.db_auth == 'iam':
        import boto3
        options['password'] = boto3.client('rds', region_name=settings.region).generate_db_auth_token(
            DBHostname=options['host'], Port=int(options.get('port', 5432)),
            DBUsername=options['user'], Region=settings.region)
    options['connect_timeout'] = 10
    with psycopg.connect(**options, row_factory=dict_row, autocommit=True) as conn:
        conn.execute('SET default_transaction_read_only=on')
        conn.execute("SET search_path TO core,public")
        conn.execute("SET statement_timeout TO '30s'")
        role = conn.execute('''SELECT rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls
          FROM pg_roles WHERE rolname=current_user''').fetchone()
        writable = conn.execute('''SELECT 1 FROM pg_tables WHERE schemaname='core' AND
          (has_table_privilege(current_user,format('%I.%I',schemaname,tablename),'INSERT') OR
           has_table_privilege(current_user,format('%I.%I',schemaname,tablename),'UPDATE') OR
           has_table_privilege(current_user,format('%I.%I',schemaname,tablename),'DELETE') OR
           has_table_privilege(current_user,format('%I.%I',schemaname,tablename),'TRUNCATE')) LIMIT 1''').fetchone()
        can_create = conn.execute("SELECT has_schema_privilege(current_user,'core','CREATE') AS allowed").fetchone()
        require(role is not None and not any(role.values()) and not writable and not can_create['allowed'], 'reader_has_write_privileges')
        tls = conn.execute('SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()').fetchone()
        require(tls is not None and tls['ssl'], 'database_tls_required')
        current = conn.execute('SELECT release_id FROM core.active_release WHERE singleton').fetchone()
        require(current is not None and str(current['release_id']) == RELEASE, 'unexpected_active_release')
        yield conn


def create_app(settings=None, *, connector=None, store=None):
    settings = settings or Settings.from_env()
    require(len(settings.token) >= 32, 'api_token_too_short')
    if store is None:
        import boto3
        from botocore.config import Config
        client = boto3.client('s3', region_name=settings.region,
            config=Config(connect_timeout=5, read_timeout=30, retries={'mode': 'standard', 'max_attempts': 3}))
        store = S3Store(client, settings.bucket, settings.root_key, settings.prefix)
    connector = connector or (lambda: database(settings))
    app = FastAPI(title='ETL4 five-hole private cloud pilot', version='0.1.0',
                  docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware('http')
    async def guard(request, call_next):
        supplied = request.headers.get('authorization', '')
        if not hmac.compare_digest(supplied.encode(), ('Bearer ' + settings.token).encode()):
            return JSONResponse({'error': 'authentication_required'}, status_code=401,
                                headers={'WWW-Authenticate': 'Bearer'})
        try:
            response = await call_next(request)
        except APIError as exc:
            return JSONResponse({'error': exc.code}, status_code=exc.status)
        except Exception:
            # Provider and libpq exceptions can contain hosts, paths or credentials.
            return JSONResponse({'error': 'backend_unavailable'}, status_code=503)
        response.headers['Cache-Control'] = 'private, no-store'
        response.headers['X-Data-Release'] = RELEASE
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response

    @app.get('/health')
    def health():
        with connector() as conn:
            count = conn.execute('SELECT count(*) AS n FROM core.release_dataset WHERE release_id=%s', (RELEASE,)).fetchone()['n']
            require(count == 5, 'release_dataset_count_mismatch')
        return {'status': 'ok', 'release_id': RELEASE, 'database': 'reachable',
                'media_backend': 's3', 'media_verified_by_health': False}

    @app.get('/v1/holes')
    def holes():
        with connector() as conn:
            items = [{'hole_id': hole, **context(conn, hole)} for hole in HOLES]
        return {'release_id': RELEASE, 'items': items}

    @app.get('/v1/holes/{hole}/logs')
    def list_logs(hole: str):
        with connector() as conn:
            ctx = context(conn, hole)
            items = [{k: log[k] for k in ('id', 'source_log_name', 'log_kind', 'availability_status',
                'binding_status', 'metric_key', 'unit', 'output_region', 'variant_code')}
                for log in logs(conn, ctx['dataset_revision_id'])]
            images = conn.execute('''SELECT id,source_log_name,log_kind,availability_status FROM core.scan_log
              WHERE dataset_revision_id=%s AND log_kind='image' ORDER BY source_log_name,id''',
              (ctx['dataset_revision_id'],)).fetchall()
        return {'release_id': RELEASE, 'hole_id': hole, 'items': items, 'image_logs': images}

    @app.get('/v1/holes/{hole}/samples/{sample_no}')
    def sample(hole: str, sample_no: int = Path(ge=0),
               log_id: list[UUID] = Query(default=[], max_length=16), image_log_id: UUID | None = None):
        with connector() as conn:
            return read_sample(conn, store, hole, sample_no, log_id, image_log_id)

    @app.get('/v1/images/{asset_id}/content')
    def image(asset_id: UUID):
        with connector() as conn:
            allowed = conn.execute('''SELECT 1 FROM core.image_region_asset ra
              JOIN core.image_region r ON r.id=ra.region_id
              JOIN core.release_dataset rd ON rd.dataset_revision_id=r.dataset_revision_id
              WHERE ra.asset_id=%s AND rd.release_id=%s AND ra.representation_kind='native_lossless_png'
              AND r.region_status='reviewed' LIMIT 1''', (str(asset_id), RELEASE)).fetchone()
            if not allowed:
                raise APIError('image_not_in_release', 404)
            asset = store.asset(conn, str(asset_id))
            if asset is None:
                raise APIError('asset_unavailable', 503)
            require(asset['media_type'] == 'image/png', 'unexpected_image_type')
            data = store.full(asset)
        return Response(data, media_type='image/png', headers={'ETag': f'"{asset["sha256"]}"'})

    return app
