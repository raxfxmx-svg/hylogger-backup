"""Build an isolated, read-only AWS audit using the owner's existing validators."""
import ast
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
CODE = HERE.parents[1] / 'database'
parts = ['''import base64, gzip, hashlib, io, json, re, ssl, sys, traceback, zipfile
from pathlib import Path
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from collections import Counter
import boto3
import psycopg
from psycopg.rows import dict_row

def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False, default=str) + "\\n").encode("utf-8")
def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()
def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def safe_child(root, relative):
    root=Path(root).resolve()
    path=(root/relative).resolve()
    if path == root or not path.is_relative_to(root):
        raise ValueError("Unsafe relative path")
    return path
''']
source = (CODE / '_batch_files.py').read_text(encoding='utf-8-sig')
names = {'require','checksum','object_key','file_info','read_json','check_file_info','local_file','load_export'}
for node in ast.parse(source).body:
    if isinstance(node, ast.Assign) and any(isinstance(n, ast.Name) and n.id in {'FORMAT','DATA_TABLES','EVIDENCE_TABLES','RELEASE_TABLES','ADMIN_TABLES','KNOWN_TABLES'} for n in node.targets):
        parts.append(ast.get_source_segment(source,node))
    elif isinstance(node,ast.FunctionDef) and node.name in names:
        parts.append(ast.get_source_segment(source,node))
source = (CODE / '40_merge_cloud_batch.py').read_text(encoding='utf-8-sig')
for node in ast.parse(source).body:
    if isinstance(node,ast.FunctionDef) and node.name in {'local_acceptance_evidence','inspect_columns'}:
        parts.append(ast.get_source_segment(source,node))
migrations=[{'name':p.name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted((CODE/'migrations').glob('*.sql'))]
parts.append('OWNER_MIGRATIONS = '+repr(migrations))
parts.append((HERE/'audit_body.py').read_text(encoding='utf-8'))
target = HERE / 'audit_BSDD023_20261011.py'
target.write_text('\n\n'.join(parts),encoding='utf-8')
compile(target.read_text(encoding='utf-8'),str(target),'exec')
print(json.dumps({'script':str(target),'bytes':target.stat().st_size,'sha256':hashlib.sha256(target.read_bytes()).hexdigest()}))
