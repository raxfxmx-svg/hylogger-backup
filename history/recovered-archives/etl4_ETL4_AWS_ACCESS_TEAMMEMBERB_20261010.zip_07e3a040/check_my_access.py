"""Teammate smoke check using their own AWS login. Performs no cloud writes."""
import json
import os
import ssl
import tempfile
import boto3
import psycopg
from psycopg.rows import dict_row

REGION = "ap-southeast-2"
HOST = "db.example.com"
BUCKET = "hyloggerdemo-000000000000-ap-southeast-2-an"
session = boto3.Session(region_name=REGION)
identity = session.client("sts").get_caller_identity()
assert identity["Arn"] == "arn:aws:iam::000000000000:user/teammemberb.Contributor4", "Sign in as teammemberb.Contributor4 for this check."
rds = session.client("rds")
cluster = rds.describe_db_clusters(DBClusterIdentifier="database-1")["DBClusters"][0]
assert cluster["Endpoint"] == HOST
report = {"identity": identity["Arn"], "metadata_access": "passed", "database_roles": []}
fd, ca_path = tempfile.mkstemp(suffix=".pem", prefix="etl4-trusted-ca-")
try:
    with os.fdopen(fd, "w", encoding="ascii") as out:
        roots = ssl.create_default_context().get_ca_certs(binary_form=True)
        assert roots, "No trusted CA certificates found on this computer."
        out.write("".join(ssl.DER_cert_to_PEM_cert(cert) for cert in roots))
    for role in ("etl4_reader", "etl4_teammemberb_dev"):
        token = rds.generate_db_auth_token(DBHostname=HOST, Port=5432, DBUsername=role)
        with psycopg.connect(host=HOST, port=5432, dbname="etl4_core", user=role, password=token,
            sslmode="verify-full", sslrootcert=ca_path, connect_timeout=60,
            autocommit=True, row_factory=dict_row) as conn:
            conn.execute("SET default_transaction_read_only=on")
            row = conn.execute("""SELECT a.release_id::text, count(distinct d.borehole_id) holes,count(*) datasets
                FROM core.active_release a JOIN core.release_dataset rd ON rd.release_id=a.release_id
                JOIN core.dataset d ON d.id=rd.dataset_id GROUP BY a.release_id""").fetchone()
            assert row and row["holes"] > 0
            report["database_roles"].append({"role": role, "catalogue": row})
            if role == "etl4_reader":
                asset = conn.execute("""SELECT object_key FROM core.asset_location
                    WHERE backend='s3' AND access_status='verified_remote'
                    AND root_key='etl4_s3_a22098dedb6798558858'
                    ORDER BY object_key LIMIT 1""").fetchone()
    s3 = session.client("s3")
    s3.list_objects_v2(Bucket=BUCKET, Prefix="etl4/objects/sha256/", MaxKeys=1)
    response = s3.get_object(Bucket=BUCKET, Key=asset["object_key"], Range="bytes=0-63")
    try:
        assert response["Body"].read(64)
    finally:
        response["Body"].close()
    report["s3_list_and_get"] = "passed"
    report["status"] = "passed"
    print(json.dumps(report, indent=2))
finally:
    os.unlink(ca_path)

