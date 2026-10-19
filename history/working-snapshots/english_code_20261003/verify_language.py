"""Check language coverage, unchanged operations, and synchronized upload files."""
import ast
import copy
import hashlib
import io
import json
from pathlib import Path
import re
import tokenize

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
HAN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
ENGLISH = re.compile(r"[A-Za-z]{2,}")
CHINESE_PUNCT = re.compile(r"[，。；：！？、【】（）‘’“”]")
selection = json.loads((HERE / "selection_before.json").read_text(encoding="utf-8-sig"))


def doc_nodes(tree):
    return [node.body[0].value for node in ast.walk(tree)
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            and node.body and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant) and isinstance(node.body[0].value.value, str)]


class Operations(ast.NodeTransformer):
    def visit_JoinedStr(self, node):
        node.values = [self.visit(value) for value in node.values if isinstance(value, ast.FormattedValue)]
        return node

    def visit_Subscript(self, node):
        if (isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Attribute)
                and isinstance(node.value.func.value, ast.Name) and node.value.func.value.id == "__doc__"
                and node.value.func.attr == "splitlines" and not node.value.args and not node.value.keywords
                and isinstance(node.slice, ast.Constant) and node.slice.value == 0):
            return ast.Name(id="__doc__", ctx=ast.Load())
        return self.generic_visit(node)

    def visit_Constant(self, node):
        if isinstance(node.value, str):
            return ast.copy_location(ast.Constant(value="<text>"), node)
        return node


def operations(tree):
    return ast.dump(Operations().visit(copy.deepcopy(tree)), include_attributes=False)


results = []
errors = []
for item in selection["files"]:
    path = ROOT / item["source"]
    original = (HERE / "before" / item["source"]).read_text(encoding="utf-8-sig")
    source = path.read_text(encoding="utf-8-sig")
    before, tree = ast.parse(original), ast.parse(source)
    compile(source, str(path), "exec")
    docs = doc_nodes(tree)
    doc_ids = {id(node) for node in docs}
    issues = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in doc_ids:
            if HAN.search(node.value) or CHINESE_PUNCT.search(node.value):
                issues.append({"kind": "runtime_chinese", "line": node.lineno, "text": node.value})
        if isinstance(node, ast.Name) and HAN.search(node.id):
            issues.append({"kind": "identifier", "line": node.lineno, "text": node.id})
    for node in docs:
        if not (HAN.search(node.value) and ENGLISH.search(node.value)):
            issues.append({"kind": "docstring_not_bilingual", "line": node.lineno, "text": node.value})
        if HAN.search(node.value.splitlines()[0]):
            issues.append({"kind": "docstring_first_line_not_english", "line": node.lineno})
    comments = []
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type == tokenize.COMMENT:
            value = token.string.lstrip("# ")
            if not value or not (HAN.search(value) or ENGLISH.search(value)):
                continue
            comments.append(token)
            if not (HAN.search(value) and ENGLISH.search(value)):
                issues.append({"kind": "comment_not_bilingual", "line": token.start[0], "text": value})
    if operations(before) != operations(tree):
        issues.append({"kind": "operation_AST_changed"})
    target = ROOT / 'github-upload' / item["path"]
    if path.read_bytes() != target.read_bytes():
        issues.append({"kind": "upload_copy_differs"})
    item_result = {"file": item["source"], "upload": item["path"], "docstrings": len(docs),
                   "comments": len(comments), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "issues": issues}
    results.append(item_result)
    errors.extend({"file": item["source"], **issue} for issue in issues)

def assignment(file, key):
    tree = ast.parse(file.read_text(encoding="utf-8-sig"))
    return next(ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign)
                and isinstance(node.targets[0], ast.Name) and node.targets[0].id == key)

metadata = Path("etl4/processing/metadata_normalization.py")
old_metrics = assignment(HERE / "before" / metadata, "METRICS")
new_metrics = assignment(ROOT / metadata, "METRICS")
assert old_metrics.keys() == new_metrics.keys()
assert all(old_metrics[key][0:1] + old_metrics[key][2:] == new_metrics[key][0:1] + new_metrics[key][2:] for key in old_metrics)
rules = Path("etl4/processing/_etl_common.py")
old_rule = assignment(HERE / "before" / rules, "PROCESSING_RULE_VERSION")
new_rule = assignment(ROOT / rules, "PROCESSING_RULE_VERSION")
assert old_rule == "etl4-preparation-v2" and new_rule == "etl4-preparation-v3"

report = {"status": "passed" if not errors else "failed", "python_files": len(results),
          "bilingual_docstrings": sum(item["docstrings"] for item in results),
          "bilingual_comments": sum(item["comments"] for item in results),
          "runtime_chinese_occurrences": sum(issue["kind"] == "runtime_chinese" for issue in errors),
          "metric_labels_translated": sum(old_metrics[key][1] != new_metrics[key][1] for key in old_metrics),
          "metric_keys_types_units_unchanged": True, "old_rule": old_rule, "new_rule": new_rule,
          "results": results, "errors": errors}
(HERE / "language_verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({key: value for key, value in report.items() if key != "results"}, ensure_ascii=False, indent=2))
raise SystemExit(bool(errors))
