"""Check source copies and documentation without running ETL."""
import ast
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
UPLOAD = ROOT / 'github-upload'


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


proof = read_json(HERE / "final_code_verification.json")
expected = {item["path"] for item in proof["files"]}
assert expected == {p.relative_to(UPLOAD).as_posix() for p in UPLOAD.rglob("*.py")}
for item in proof["files"]:
    source = ROOT / item["source"]
    target = UPLOAD / item["path"]
    data = source.read_bytes()
    assert data == target.read_bytes(), item["path"]
    tree = ast.parse(data.decode("utf-8-sig"), filename=str(source))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        else:
            continue
        assert not any(name.startswith("_legacy") or "handoff" in name for name in names), item["path"]
    item.update(bytes=len(data), lines=len(data.splitlines()), sha256=hashlib.sha256(data).hexdigest())
assert [p.name for p in (UPLOAD / 'review-and-recovery').rglob("*.py")] == ["14_verify_database_backup.py"]
docs = sorted(UPLOAD.rglob("*.md"))
assert len(docs) == 3
assert len(list(UPLOAD.rglob("*.*"))) == 56
checked_links = 0
for doc in docs + [ROOT / "etl4/database/PUBLIC_MODULE_SIMPLIFICATION_20261003.md"]:
    content = doc.read_text(encoding="utf-8-sig")
    for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", content):
        if "://" in target or target.startswith("#"):
            continue
        local = unquote(target.split("#", 1)[0]).strip("<>")
        assert (doc.parent / local).exists(), (str(doc), target)
        checked_links += 1

before = ast.parse((HERE / "code_before/etl4/database/_schema_docs.py").read_text(encoding="utf-8-sig"))
after = ast.parse((ROOT / "etl4/database/_schema_docs.py").read_text(encoding="utf-8-sig"))
functions = lambda tree: [ast.dump(node, include_attributes=False) for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
assert functions(before) == functions(after)
proof["new_python_bytes"] = sum(item["bytes"] for item in proof["files"])
proof["schema_docs_functions_unchanged"] = True
proof["readme_links_checked"] = checked_links
(HERE / "final_code_verification.json").write_text(json.dumps(proof, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({key: value for key, value in proof.items() if key not in ("files", "db_and_publication_function_AST_unchanged")}, ensure_ascii=False))
