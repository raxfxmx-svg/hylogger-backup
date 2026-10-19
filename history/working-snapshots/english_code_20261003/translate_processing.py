import ast
import io
import json
import re
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FILES = [ROOT / "etl4/processing" / p.name for p in (ROOT / 'github-upload/etl4/processing').glob("*.py")]
FILES += [ROOT / "etl4/_settings.py", ROOT / "etl4/_file_checks.py"]
DOCS = {
    '\u5148\u68c0\u67e5 raw \u6587\u4ef6\u662f\u5426\u9f50\u5168\uff0c\u518d\u5206\u51fa\u5355 dataset\u3001\u591a dataset \u548c\u5f85\u5904\u7406\u94bb\u5b54\u3002': "Check raw files and separate single-dataset, multi-dataset, and pending boreholes.",
    '\u6e05\u5355\u4e2d\u7684\u8def\u5f84\u5fc5\u987b\u7559\u5728\u5f53\u524d\u5b54\u5185\u3002': "Keep manifest paths inside the current borehole directory.",
    '\u6e05\u70b9\u9009\u5b9a\u94bb\u5b54\u7684\u539f\u59cb\u6587\u4ef6\uff0c\u4e3a\u540e\u7eed\u5185\u5bb9\u6821\u9a8c\u5efa\u7acb\u6e05\u5355\u3002': "Inventory raw files for the selected boreholes before content validation.",
    '\u9010\u6587\u4ef6\u68c0\u67e5\u54c8\u5e0c\u4e0e\u6570\u636e\u683c\u5f0f\uff0c\u4fdd\u7559\u53ef\u89e3\u91ca\u7684\u6765\u6e90\u95ee\u9898\u3002': "Check file hashes and formats while recording explainable source issues.",
    '\u6574\u7406\u5143\u6570\u636e\u548c\u6765\u6e90\u6807\u8bc6\uff0c\u540c\u65f6\u4fdd\u5b58\u539f\u59cb\u6587\u6863\u3002': "Normalize metadata and source identifiers while preserving original documents.",
    '\u5efa\u7acb\u6837\u672c\u5e8f\u53f7\u4e0e\u5b54\u6df1\u7684\u5bf9\u5e94\u5173\u7cfb\uff0c\u6838\u5bf9\u6258\u76d8\u548c\u884c\u6bb5\u8303\u56f4\u3002': "Map sample indices to depths and check tray and section ranges.",
    '\u751f\u6210 Parquet \u6587\u4ef6\uff0c\u5e76\u56de\u8bfb\u6bd4\u8f83\u6570\u503c\u3001\u7a7a\u503c\u548c\u884c\u6570\u3002': "Write Parquet files and read them back to compare values, nulls, and row counts.",
    '\u6838\u5bf9\u51c6\u5907\u7ed3\u679c\u53ca\u6309\u5b54\u6df1\u8bfb\u53d6\u7684\u7ed3\u679c\uff0c\u4e0d\u6539\u5199\u6570\u636e\u5185\u5bb9\u3002': "Check prepared data and depth-based reads without changing data content.",
    '\u6309\u7c7b\u578b\u548c\u503c\u8ba1\u7b97\u6458\u8981\uff0c\u4e0d\u4f9d\u8d56 Parquet \u538b\u7f29\u548c\u5b57\u5178\u7f16\u7801\u3002': "Hash types and values independently of Parquet compression and dictionary encoding.",
    '\u6309\u9009\u5b9a dataset \u89e3\u6790\uff0c\u5e76\u5728\u9996\u6b21\u5199\u5165\u65f6\u4fdd\u5b58\u5b8c\u6574\u6765\u6e90\u53ca\u7f3a\u5931\u539f\u56e0\u3002': "Parse selected datasets and record complete provenance and missing-data reasons on the first write.",
    '\u5904\u7406\u6b65\u9aa4\u4f7f\u7528\u7684\u6587\u4ef6\u8bfb\u5199\u3001\u89c4\u5219\u7248\u672c\u548c dataset \u4e0a\u4e0b\u6587\u3002': "Provide file I/O, rule versions, and dataset context for processing steps.",
    '\u5355\u4e2a dataset \u7684\u89e3\u6790\u8f93\u5165\uff0c\u907f\u514d\u4e34\u65f6\u4fee\u6539\u5176\u4ed6\u6a21\u5757\u3002': "Provide parsing inputs for one dataset without temporarily changing other modules.",
    '\u5bf9\u9f50\u65f6\u6309\u9700\u91cd\u8bfb\u5e76\u68c0\u67e5\u5185\u5bb9\uff0c\u6b65\u9aa4 2 \u5df2\u5b8c\u6210\u5b8c\u6574\u683c\u5f0f\u6821\u9a8c\u3002': "Reread and check content during alignment; step 2 has already validated full formats.",
    '\u8fd0\u884c\u914d\u7f6e\u7531\u7f16\u53f7\u5165\u53e3\u521d\u59cb\u5316\uff1b\u5bfc\u5165\u672c\u6a21\u5757\u4e0d\u4f1a\u89e3\u6790\u547d\u4ee4\u884c\u3002': "Initialize run settings in numbered entry points; importing this module does not parse arguments.",
    '\u62a5\u544a\u6587\u4ef6\u540d\u4fdd\u6301\u77ed\u5c0f\uff1b\u6279\u6b21\u6807\u7b7e\u4e0d\u53c2\u4e0e\u6570\u636e\u7248\u672c\u8ba1\u7b97\u3002': "Keep report filenames short; batch labels do not contribute to data version identities.",
    '\u68c0\u67e5\u672c\u6b21\u660e\u786e\u9009\u62e9\u7684\u5b54\u53f7\uff0c\u907f\u514d\u628a\u76ee\u5f55\u8def\u5f84\u5f53\u4f5c\u5b54\u53f7\u3002': "Validate explicitly selected borehole IDs so directory paths cannot be mistaken for IDs.",
    '\u4e00\u4e2a\u8fdb\u7a0b\u8fd0\u884c\u4e00\u4e2a\u6b65\u9aa4\uff0c\u516c\u5171\u5de5\u5177\u4f7f\u7528\u8be5\u6b65\u9aa4\u9009\u5b9a\u7684\u76ee\u5f55\u548c\u6570\u636e\u5e93\u3002': "Run one step per process with shared utilities using its selected directories and database.",
    '\u6e05\u5355\u53ea\u4fdd\u5b58\u76f8\u5bf9\u8def\u5f84\uff0c\u4e0d\u80fd\u901a\u8fc7\u7edd\u5bf9\u8def\u5f84\u3001.. \u6216\u94fe\u63a5\u8d8a\u51fa\u6839\u76ee\u5f55\u3002': "Restrict manifest paths to the root, rejecting absolute paths, parent traversal, and escaping links.",
    '\u65e7\u8def\u5f84\u4fdd\u6301\u539f\u6837\uff1b\u5916\u90e8 raw/work \u7528\u6839\u76ee\u5f55\u952e\u5b9a\u4f4d\uff0c\u4e0d\u5199\u5165\u76d8\u7b26\u3002': "Preserve existing paths and reference external raw/work directories by root keys without drive letters.",
    '\u547d\u4ee4\u884c/\u6279\u6b21\u76ee\u5f55\u5141\u8bb8\u663e\u5f0f\u7edd\u5bf9\u8def\u5f84\uff0c\u6e05\u5355\u5185\u90e8\u4ecd\u4f7f\u7528\u53d7\u9650\u76f8\u5bf9\u5f15\u7528\u3002': "Allow explicit absolute CLI/batch directories while keeping manifest references relative and restricted.",
    '\u5165\u53e3\u89e3\u6790\u5b8c\u53c2\u6570\u540e\u8c03\u7528\u4e00\u6b21\uff0c\u540e\u7eed\u4e1a\u52a1\u51fd\u6570\u6309\u9700\u663e\u5f0f\u63a5\u6536\u76ee\u5f55\u3002': "Configure once after parsing arguments; subsequent processing functions receive directories as needed.",
    '\u6240\u6709\u7f16\u53f7\u5165\u53e3\u63a5\u53d7\u76f8\u540c\u7684\u5de5\u4f5c\u76ee\u5f55\u548c\u6570\u636e\u5e93\u53c2\u6570\u3002': "Give numbered entry points the same working-directory and database arguments.",
    '\u4e00\u6b21\u6821\u9a8c\u4e2d\u7684\u6587\u4ef6\u54c8\u5e0c\u53bb\u91cd\u548c\u5b9e\u9645\u626b\u63cf\u8ba1\u6570\u3002': "Deduplicate file hashes within one check and count actual file scans.",
    '\u8fd0\u884c\u8bb0\u5f55\u5355\u72ec\u4fdd\u5b58\uff0c\u4e0d\u5199\u5165\u6570\u636e\u8eab\u4efd\u6216\u51c6\u5907\u7ed3\u679c\u3002': "Save run records separately from data identities and prepared results.",
}
COMMENTS = {
    '\u8fd9\u91cc\u53ea\u68c0\u67e5\u6587\u4ef6\u548c\u6e05\u5355\uff0c\u4e0d\u89e3\u6790\u5927\u6587\u4ef6\uff0c\u4e5f\u4e0d\u8fde\u63a5\u6570\u636e\u5e93\u3002': "Check only files and manifests; do not parse large payloads or connect to the database.",
    '\u672a\u63d0\u4f9b\u7684\u6570\u636e\u6709\u65f6\u4ecd\u5e26\u5360\u4f4d\u6587\u4ef6\u540d\uff0c\u4e0d\u80fd\u5c06\u5176\u5f53\u6210\u6f0f\u4e0b\u8f7d\u3002': "Unavailable data may still have placeholder filenames; these are not missed downloads.",
    '\u56fe\u7247\u6e05\u5355\u4e5f\u5305\u542b mosaics\uff1b\u5355\u6709\u62fc\u56fe\u4e0d\u80fd\u4ee3\u66ff images \u4e2d\u7684\u5b54\u56fe\u3002': "Image manifests also list mosaics; mosaics alone cannot replace borehole images in images/.",
    '\u6258\u76d8\u548c\u884c\u6bb5\u662f\u540e\u7eed\u5efa\u7acb\u6837\u672c\u8f74\u7684\u5fc5\u8981\u8f93\u5165\uff1b\u6b64\u5904\u53ea\u6838\u5bf9\u5f15\u7528\u5b58\u5728\u3002': "Trays and sections are needed for the sample axis; only check reference existence here.",
    '\u540d\u5355\u548c\u62a5\u544a\u5168\u90e8\u5199\u597d\uff0c\u5165\u53e3\u624d\u53ef\u4f7f\u7528\u8fd9\u4e00\u8f6e\u7ed3\u679c\u3002': "Entry points may use this run only after all lists and reports have been written.",
    '\u6a21\u62df\u6309\u5b54\u6df1\u68c0\u7d22\u7684\u5b9e\u9645\u5b58\u50a8\u7d22\u5f15\u8bfb\u53d6\u3002': "Exercise the stored index used by depth-based queries.",
    '\u5148\u8f6c\u6362\u4e3a Python \u503c\u518d\u8ba1\u7b97\u6458\u8981\uff0c\u907f\u5f00\u6b64 Windows \u73af\u5883\u7684 Arrow \u7a7a\u503c\u586b\u5145\u6545\u969c\uff1b\u4e0d\u586b\u8865\u79d1\u5b66\u6570\u636e\u3002': "Hash Python values to avoid this Windows Arrow null-fill issue without filling scientific data.",
    '\u6bcf\u4e2a NPZ \u6570\u7ec4\u53ea\u89e3\u538b\u4e00\u6b21\uff0c\u907f\u514d\u9010\u884c\u91cd\u590d\u89e3\u538b\u3002': "Decompress each NPZ array once instead of decompressing it again for every row.",
    '\u6765\u6e90\u4f7f\u7528\u5341\u8fdb\u5236\u5b54\u6df1\uff0c\u6bd4\u8f83\u65f6\u907f\u514d\u4e8c\u8fdb\u5236\u820d\u5165\u5f71\u54cd 0.00001 \u7c73\u8fb9\u754c\u3002': "Source depths are decimal; avoid binary rounding at the 0.00001 m boundary.",
    '\u53ea\u6709\u5b57\u8282\u6570\u6b63\u786e\uff0c\u8fd8\u4e0d\u80fd\u8bc1\u660e\u5149\u8c31\u4e0e\u6837\u672c\u8f74\u5bf9\u5e94\u3002': "A matching byte count alone does not establish alignment with the sample axis.",
    '\u4ec5\u67d0\u4e2a\u6765\u6e90 dataset \u6539\u89c4\u5219\u65f6\uff0c\u5728\u8fd9\u91cc\u586b\u5199\u5176\u7248\u672c\u3002': "Set a dataset-specific version here only when its processing rules change.",
    '\u89c4\u5219\u6539\u53d8\u65f6\u63d0\u5347\u7248\u672c\uff1b\u6e90\u7801\u548c\u73af\u5883\u4ec5\u5199\u5165\u72ec\u7acb\u8fd0\u884c\u8bb0\u5f55\u3002': "Bump versions for rule changes; record source code and environment only in separate run records.",
    '\u6839\u76ee\u5f55\u952e\u5e26\u4f4d\u7f6e\u6458\u8981\uff0c\u5207\u6362\u6279\u6b21\u65f6\u4e0d\u4f1a\u8bef\u8bfb\u53e6\u4e00\u4e2a\u5de5\u4f5c\u76ee\u5f55\u3002': "Root keys include a location hash to avoid reading another working directory when switching batches.",
    '\u6bcf\u6b21\u72ec\u7acb\u5bfc\u5165\u6216\u53d1\u5e03\u91cd\u65b0\u8bfb\u53d6\uff0c\u7f13\u5b58\u4e0d\u8de8\u8c03\u7528\u4fdd\u5b58\u3002': "Reread files for each independent import or publication; do not cache across calls.",
    '\u5165\u53e3\u5df2\u7ecf\u9009\u5b9a\u914d\u7f6e\uff0c\u518d\u5c06\u8fd0\u884c\u8bb0\u5f55\u5199\u5165\u5bf9\u5e94\u76ee\u5f55\u3002': "Write the run record to the directory selected by the entry point configuration.",
}
TEXT = {
    '\u660e\u786e\u9009\u62e9\u7684\u5b54\u53f7': "Explicitly selected borehole IDs",
    '\u6b65\u9aa4 0 \u751f\u6210\u7684\u5b54\u53f7\u540d\u5355\uff0c\u6bcf\u884c\u4e00\u4e2a': "Borehole list from step 0, one ID per line",
    '\u6b65\u9aa4 0 \u672a\u5b8c\u6210\uff0c\u8bf7\u91cd\u65b0\u9884\u68c0\u540e\u4f7f\u7528\u540d\u5355': "Step 0 is incomplete; rerun the precheck before using the list",
    '\u540d\u5355\u4e0e\u6b65\u9aa4 0 \u5206\u7c7b\u4e0d\u4e00\u81f4\uff0c\u5f85\u5904\u7406\u5b54\u4e0d\u80fd\u76f4\u63a5\u8fdb\u5165\u6b63\u5e38\u6279\u6b21': "The list does not match step 0 classification; pending boreholes cannot enter a normal batch",
    '\u5fc5\u987b\u660e\u786e\u9009\u62e9\u81f3\u5c11\u4e00\u4e2a\u94bb\u5b54': "Explicitly select at least one borehole",
    '\u5b54\u53f7\u53ea\u80fd\u5305\u542b\u5b57\u6bcd\u3001\u6570\u5b57\u3001\u4e0b\u5212\u7ebf\u548c\u8fde\u5b57\u7b26': "Borehole IDs may contain only letters, digits, underscores, and hyphens",
    '\u8f93\u5165\u6e05\u5355\u4e2d\u6709\u91cd\u590d\u5b54\u53f7': "The input list contains duplicate borehole IDs",
    '\u6587\u4ef6\u8def\u5f84\u5fc5\u987b\u662f\u6839\u76ee\u5f55\u5185\u7684\u76f8\u5bf9\u8def\u5f84': "File paths must be relative paths within the root directory",
    '\u6587\u4ef6\u8def\u5f84\u8d8a\u51fa\u6839\u76ee\u5f55': "The file path escapes the root directory",
    '\u6587\u4ef6\u4e0d\u5728\u672c\u6b21 raw\u3001work \u6216 etl4 \u76ee\u5f55\u5185': "The file is outside the configured raw, work, and etl4 directories",
    '\u6587\u4ef6\u5f15\u7528\u7f3a\u5c11\u76f8\u5bf9\u8def\u5f84': "The file reference is missing its relative path",
    '\u672a\u77e5\u6587\u4ef6\u6839\u76ee\u5f55\uff0c\u8bf7\u4f7f\u7528\u751f\u6210\u672c\u6279\u6e05\u5355\u65f6\u7684 --raw-dir \u548c --work-dir': "Unknown file root; use the --raw-dir and --work-dir that generated this batch manifest",
    '\u672c\u6b21\u914d\u7f6e\u6ca1\u6709\u8be5\u8d44\u4ea7\u7684\u6839\u76ee\u5f55': "The asset root directory is not defined in the current configuration",
    '\u5de5\u4f5c\u76ee\u5f55\u5fc5\u987b\u662f\u72ec\u7acb\u5b50\u76ee\u5f55\uff0c\u4e0d\u80fd\u8986\u76d6\u6e90\u7801\u6839\u76ee\u5f55': "The working directory must be a separate subdirectory and cannot contain the source root",
    '\u5de5\u4f5c\u76ee\u5f55\u4e0d\u80fd\u8986\u76d6\u6570\u636e\u5e93\u4ee3\u7801\u6216\u5904\u7406\u4ee3\u7801': "The working directory cannot overlap database or processing code",
    '\u5de5\u4f5c\u76ee\u5f55\u4e0e raw \u76ee\u5f55\u4e0d\u80fd\u91cd\u53e0': "The working directory and raw directory cannot overlap",
    '\u8bf7\u6307\u5b9a\u672c\u5730\u6279\u6b21\u5e93\u540d\uff0c\u4e0d\u80fd\u8986\u76d6\u65e7\u4ea4\u4ed8\u5e93 etl4_core': "Specify a local batch database name; the existing etl4_core delivery database cannot be overwritten",
    '\u6309\u5b54\u5206\u76ee\u5f55\u7684\u539f\u59cb\u6570\u636e\u4f4d\u7f6e\uff0c\u76f4\u63a5\u8bfb\u53d6\u4e0d\u590d\u5236': "Raw data organized by borehole, read directly without copying",
    '\u72ec\u7acb\u8fd0\u884c\u76ee\u5f55': "Separate working directory",
    '\u72ec\u7acb\u6570\u636e\u5e93\u540d\u79f0': "Separate database name",
    '\u5df2\u6709\u672c\u5730\u5b9e\u4f8b\u7684\u8fde\u63a5\u914d\u7f6e\uff1b\u8bbe\u7f6e DSN \u65f6\u53ef\u7701\u7565': "Connection settings for an existing local instance; optional when a DSN is set",
    '\u6587\u4ef6\u5728\u8bfb\u53d6\u671f\u95f4\u53d1\u751f\u53d8\u5316\uff1a': "File changed while being read: ",
    '\u540c\u4e00\u5904\u7406\u7248\u672c\u4ea7\u751f\u4e86\u4e0d\u540c\u5185\u5bb9\uff0c\u8bf7\u68c0\u67e5\u89c4\u5219\u7248\u672c\uff1a': "The same processing version produced different content; check the rule version: ",
    '\u5904\u7406\u8303\u56f4\u4e0e\u6b65\u9aa4 1 \u4e0d\u4e00\u81f4\uff0c\u8bf7\u4f7f\u7528\u539f\u540d\u5355\u6216\u72ec\u7acb\u5de5\u4f5c\u76ee\u5f55': "Processing scope differs from step 1; use the original list or a separate working directory",
    '\u5904\u7406\u89c4\u5219\u7248\u672c\u5df2\u6539\u53d8\uff0c\u8bf7\u4ece\u6b65\u9aa4 1 \u91cd\u65b0\u51c6\u5907\u8be5\u5b54': "The processing rule version changed; prepare this borehole again from step 1",
    '\u5355 dataset\uff1a1\u201310\uff0c\u518d\u6309\u9700\u8981\u6267\u884c 20\u201329': "Single dataset: steps 1–10, then steps 20–29 as needed",
    '\u591a dataset\uff1a\u5355\u72ec\u6267\u884c 31\u201335\uff0c\u5148\u6838\u5bf9\u6765\u6e90\u8bc1\u636e\u4e0e\u6765\u6e90\u53d1\u5e03': "Multiple datasets: run steps 31–35 separately after checking source evidence and the source release",
    '\u5148\u5904\u7406\u62a5\u8b66\u6216\u7a7a\u7c7b\u522b\uff0c\u518d\u9009\u62e9\u540e\u7eed\u6b65\u9aa4': "Resolve alerts or empty categories before selecting subsequent steps",
    'JSON \u9876\u5c42\u7ed3\u6784\u4e0d\u6b63\u786e': "Incorrect top-level JSON structure",
    '\u5217\u8868\u4e2d\u5b58\u5728\u975e\u5bf9\u8c61\u8bb0\u5f55': "The list contains non-object records",
    '\u7f3a\u5c11 {name}': "Missing {name}",
    '{name} \u7f3a\u5931\u6216\u4e0d\u53ef\u8bfb\u53d6\uff1a{error}': "{name} is missing or unreadable: {error}",
    '\u7f3a\u5c11\u6587\u4ef6\u540d': "Missing filename",
    '\u6587\u4ef6\u8def\u5f84\u4e0d\u5408\u6cd5\uff1a': "Invalid file path: ",
    '\u6587\u4ef6\u8def\u5f84\u8d85\u51fa\u5b54\u76ee\u5f55\uff1a': "The file path escapes the borehole directory: ",
    '{manifest_name} \u7f3a\u5c11 files \u6e05\u5355': "{manifest_name} is missing the files list",
    '{manifest_name} \u7684\u6587\u4ef6\u6e05\u5355\u683c\u5f0f\u9519\u8bef': "{manifest_name} has an invalid files list",
    '{relative} \u6807\u8bb0\u4e3a {status}\uff0c\u4f46\u5b9e\u9645\u5b58\u5728\u6587\u4ef6': "{relative} is marked {status}, but the file exists",
    '{label}\u5360\u4f4d\u8def\u5f84\u4e0d\u5408\u6cd5\uff1a{error}': "Invalid {label} placeholder path: {error}",
    "{label}\u8bb0\u5f55\u672a\u5b8c\u6210\uff1a{entry.get('log_id', relative)}\uff08{status}\uff09": "Incomplete {label} record: {entry.get('log_id', relative)} ({status})",
    '{manifest_name} \u91cd\u590d\u5217\u51fa\u6587\u4ef6\uff1a{relative}': "{manifest_name} lists the file more than once: {relative}",
    '\u6e05\u5355\u58f0\u660e\u5df2\u63d0\u4f9b\uff0c\u4f46\u6587\u4ef6\u7f3a\u5931\uff1a': "The manifest marks the file as provided, but it is missing: ",
    '\u6570\u636e\u6587\u4ef6\u4e3a\u7a7a\uff1a': "Empty data file: ",
    '\u6587\u4ef6\u5927\u5c0f\u4e0e\u6e05\u5355\u4e0d\u7b26\uff1a': "File size differs from the manifest: ",
    '{label}\u6587\u4ef6\u65e0\u6cd5\u68c0\u67e5\uff1a{error}': "Cannot check {label} file: {error}",
    '\u53d1\u73b0\u672a\u5b8c\u6210\u4e0b\u8f7d\u7684 .part \u6587\u4ef6': "Found an incomplete .part download",
    '\u5b9e\u9645\u6587\u4ef6\u672a\u5217\u4e3a\u5df2\u63d0\u4f9b\u7684\u8f7d\u8377': "The file is not listed as a provided payload",
    "{label}：{path}": "{label}: {path}",
    '\u6765\u6e90\u6807\u8bb0\u672a\u63d0\u4f9b': "Marked unavailable by the source",
    '\u7c7b\u522b\u76ee\u5f55\u4e3a\u7a7a\u6216\u4e0d\u5b58\u5728': "Category directory is empty or missing",
    '{label}\u6570\u636e\u4e3a\u7a7a\uff1a{reason}': "No {label} data: {reason}",
    '\uff0c\u65e0\u6cd5\u5efa\u7acb\u57fa\u7840\u6837\u672c': "; base samples cannot be created",
    '\uff1b\u5355\u72ec\u5904\u7406\uff0c\u4e0d\u76f4\u63a5\u4ea4\u7ed9\u5f53\u524d\u5b8c\u6574\u6570\u636e\u6d41\u7a0b': "; handle separately before using the current complete-data workflow",
    'datasets.json \u6ca1\u6709 dataset\uff0c\u65e0\u6cd5\u9009\u62e9\u5904\u7406\u6d41\u7a0b': "datasets.json contains no datasets; a processing route cannot be selected",
    'dataset \u7f3a\u5c11\u6709\u6548 dataset_id': "A dataset is missing a valid dataset_id",
    'datasets.json \u5b58\u5728\u91cd\u590d dataset_id': "datasets.json contains duplicate dataset_id values",
    'borehole.json \u7f3a\u5c11\u5b54\u53f7 nvcl_id': "borehole.json is missing the borehole ID nvcl_id",
    'borehole.json \u7684\u5b54\u53f7\u4e0e\u76ee\u5f55\u4e0d\u4e00\u81f4': "The borehole ID in borehole.json differs from the directory name",
    'package_manifest.json \u7684\u5b54\u53f7\u4e0e\u76ee\u5f55\u4e0d\u4e00\u81f4': "The borehole ID in package_manifest.json differs from the directory name",
    '\u539f\u59cb\u5305\u672a\u5b8c\u6210\uff1a': "The raw package is incomplete: ",
    '\u4e0b\u8f7d\u6e05\u5355\u8bb0\u5f55\u4e86\u9519\u8bef\uff1a': "The download manifest records errors: ",
    "dataset {dataset.get('dataset_id')} \u7f3a\u5c11 {field} \u5bf9\u5e94\u7684\u6807\u91cf\u8bb0\u5f55": "Dataset {dataset.get('dataset_id')} is missing the scalar record for {field}",
    'raw \u76ee\u5f55\u4e2d\u6ca1\u6709\u5b54\u76ee\u5f55': "The raw directory contains no borehole directories",
    '\u65e0\u6cd5\u5b8c\u6210\u9884\u68c0\uff1a': "Cannot complete the precheck: ",
    '\u53ea\u6838\u5bf9\u6e05\u5355\u3001\u6587\u4ef6\u5b58\u5728\u53ca\u5927\u5c0f\uff1b\u672a\u8ba1\u7b97\u8f7d\u8377\u54c8\u5e0c\uff0c\u672a\u9a8c\u8bc1\u4e1a\u52a1\u5185\u5bb9\uff0c\u672a\u5bfc\u5165\u6570\u636e\u5e93': "Checks manifests, file existence, and sizes only; payload hashes, business content, and database import are outside this precheck",
    '# raw \u8f93\u5165\u9884\u68c0': "# Raw input precheck",
    '\u6765\u6e90\uff1a': "Source: ",
    "\u5171 {len(holes)} \u5b54\uff0c{report['dataset_count']} \u4e2a dataset\uff1b\u8017\u65f6 {elapsed:.3f} \u79d2\u3002": "{len(holes)} boreholes, {report['dataset_count']} datasets; elapsed time: {elapsed:.3f} seconds.",
    '- {label}\uff1a{len(groups[name])} \u5b54\uff08`{name}_holes.txt`\uff09': "- {label}: {len(groups[name])} boreholes (`{name}_holes.txt`)",
    '\u9884\u68c0\u4ec5\u5206\u6d41\uff0c\u4e0d\u79fb\u52a8\u6587\u4ef6\u3001\u4e0d\u81ea\u52a8\u8fd0\u884c\u540e\u7eed\u6b65\u9aa4\u3002\u540e\u7eed\u6b65\u9aa4\u4f7f\u7528\u540c\u4e00 --raw-dir \u548c --work-dir\uff0c\u76f4\u63a5\u8bfb\u53d6\u539f\u5305\u3002': "The precheck assigns routes without moving files or starting subsequent steps. Use the same --raw-dir and --work-dir to read the original packages in subsequent steps.",
    '\u6574\u7c7b\u7f3a\u5931\u7684\u5b54\u5355\u5217\u5f85\u5904\u7406\uff1b\u8fd9\u4e0d\u8868\u793a\u6765\u6e90\u635f\u574f\uff0c\u4e5f\u4e0d\u8868\u793a\u5f53\u524d\u540e\u7eed\u4ee3\u7801\u5df2\u652f\u6301\u7a7a\u7c7b\u522b\u3002': "Boreholes with an entirely missing category are listed as pending. This does not imply source corruption or support for empty categories in subsequent steps.",
    '## \u591a dataset \u94bb\u5b54': "## Boreholes with multiple datasets",
    '| \u5b54\u53f7 | dataset \u6570 | dataset \u540d\u79f0\u548c ID | \u72b6\u6001 |': "| Borehole ID | Dataset count | Dataset names and IDs | Status |",
    '## \u7f3a\u5931\u4e0e\u62a5\u8b66': "## Missing data and alerts",
    '\u672a\u77e5\u6570\u91cf': "unknown count",
    "### {hole['hole_id']}\uff08{count} \u4e2a dataset\uff09": "### {hole['hole_id']} ({count} datasets)",
    '- \u62a5\u8b66\uff1a': "- Alert: ",
    '- \u63d0\u793a\uff1a': "- Warning: ",
    '## \u5168\u90e8\u5b54\u7684\u5206\u7c7b': "## Classification of all boreholes",
    '| \u5b54\u53f7 | dataset \u6570 | \u6807\u91cf\u6587\u4ef6 | \u5149\u8c31\u6587\u4ef6 | \u8f6e\u5ed3\u6587\u4ef6 | \u56fe\u7247\u6587\u4ef6 | \u540e\u7eed\u8def\u5f84 |': "| Borehole ID | Dataset count | Scalar files | Spectral files | Profilometer files | Image files | Next steps |",
    '\u672a\u5b8c\u6210\u68c0\u67e5': "not checked",
    '\u672a\u77e5': "unknown",
    '\u62a5\u544a\u548c\u5206\u7c7b\u540d\u5355\u4f4d\u7f6e\uff0c\u9ed8\u8ba4\u4f7f\u7528\u672c\u6279\u5de5\u4f5c\u76ee\u5f55': "Report and classified-list directory; defaults to this batch working directory",
    'raw \u76ee\u5f55\u4e0d\u5b58\u5728\uff1a': "The raw directory does not exist: ",
    '\u62a5\u544a\u8bf7\u4fdd\u5b58\u5728 raw \u76ee\u5f55\u4e4b\u5916\uff0c\u907f\u514d\u6df7\u5165\u539f\u59cb\u6587\u4ef6': "Save reports outside the raw directory to keep them separate from raw files",
    '\u9884\u68c0\u5931\u8d25\uff1a': "Precheck failed: ",
    "\u68c0\u67e5 {len(holes)} \u5b54\uff0c\u5df2\u8bc6\u522b {sum(h['dataset_count'] or 0 for h in holes)} \u4e2a dataset\u3002": "Checked {len(holes)} boreholes and identified {sum(h['dataset_count'] or 0 for h in holes)} datasets.",
    '{label}\uff1a{len(groups[name])} \u5b54': "{label}: {len(groups[name])} boreholes",
    "[\u591a dataset] {hole['hole_id']}\uff1a{hole['dataset_count']} \u4e2a": "[Multiple datasets] {hole['hole_id']}: {hole['dataset_count']}",
    "[\u62a5\u8b66] {hole['hole_id']}\uff1a{message}": "[Alert] {hole['hole_id']}: {message}",
    "[\u63d0\u793a] {hole['hole_id']}\uff1a{message}": "[Warning] {hole['hole_id']}: {message}",
    '\u62a5\u544a\uff1a': "Report: ",
    '# {hole} \u8f93\u5165\u6e05\u5355': "# {hole} Input inventory",
    "\u72b6\u6001\uff1a\u901a\u8fc7\u3002\u5171 {len(files)} \u4e2a\u6587\u4ef6\uff0c{result['source_bytes']:,} \u5b57\u8282\u3002": "Status: passed. {len(files)} files, {result['source_bytes']:,} bytes.",
    '\u672c\u6b65\u9aa4\u6838\u5bf9\u6765\u6e90\u8303\u56f4\u3001\u6587\u4ef6\u6e05\u5355\u548c\u5927\u5c0f\uff1b\u8f7d\u8377\u54c8\u5e0c\u4e0e\u7ed3\u6784\u7531\u6b65\u9aa4 2 \u9a8c\u8bc1\u3002': "This step checks source scope, file inventory, and sizes; step 2 validates payload hashes and structure.",
    '# {hole} \u6587\u4ef6\u5b8c\u6574\u6027\u68c0\u67e5': "# {hole} File integrity check",
    "\u72b6\u6001\uff1a{report['status']}\u3002": "Status: {report['status']}.",
    "\u68c0\u67e5 {counts['files_checked']} \u4e2a\u6587\u4ef6\uff1b\u6807\u91cf {counts['scalar_data_rows']:,} \u884c\uff1b\u9519\u8bef {len(errors)} \u9879\u3002": "Checked {counts['files_checked']} files and {counts['scalar_data_rows']:,} scalar rows; {len(errors)} errors.",
    '\u77ff\u7269\u540d\u79f0': "Mineral name",
    '\u77ff\u7269\u7ec4': "Mineral group",
    '\u6a21\u578b\u5206\u91cf\u6743\u91cd': "Model component weight",
    '\u62df\u5408\u8bef\u5dee': "Fit error",
    '\u6e90 SNR \u6307\u6807': "Source SNR metric",
    '\u6e90 NIL_Stat \u6307\u6807': "Source NIL_Stat metric",
    '\u6e90 Unbound_Water \u6307\u6807': "Source Unbound_Water metric",
    '\u6e90 Bound_Water \u6307\u6807': "Source Bound_Water metric",
    '\u6e90 AspRat \u6307\u6807': "Source AspRat metric",
    '\u6e90 TNorm \u6307\u6807': "Source TNorm metric",
    '# {hole} \u5143\u6570\u636e\u6807\u51c6\u5316': "# {hole} Metadata normalization",
    '\u4fdd\u7559 {len(raw)} \u4efd\u5143\u6570\u636e\u6587\u6863\u3001{len(logs)} \u6761\u65e5\u5fd7\u3001{len(sets)} \u4e2a\u89e3\u91ca\u7ed3\u679c\u7ec4\u3002': "Preserved {len(raw)} metadata documents, {len(logs)} logs, and {len(sets)} interpretation sets.",
    '\u4fdd\u5bc6\u7f3a\u5931\u3001\u7f29\u7565\u56fe\u7b56\u7565\u53ca\u672a\u786e\u8ba4\u7684\u4e13\u4e1a\u5b9a\u4e49\u5747\u4fdd\u7559\u660e\u786e\u72b6\u6001\uff0c\u672a\u751f\u6210\u53ef\u4fe1\u5ea6\u3002': "Confidentiality-related omissions, thumbnail policies, and unconfirmed domain definitions retain explicit statuses; no confidence scores were generated.",
    '# {hole} \u6837\u672c\u4e0e\u4f4d\u7f6e\u5bf9\u9f50': "# {hole} Sample and position alignment",
    '{n:,} \u4e2a\u6837\u672c\uff0c{len(dense)} \u6761\u5bc6\u96c6\u6807\u91cf\u901a\u8fc7\u9010\u5750\u6807\u54c8\u5e0c\u5bf9\u7167\uff1b': "{n:,} samples and {len(dense)} dense scalar logs passed coordinate-by-coordinate hash checks; ",
    "\u4fdd\u7559 {report['duplicate_depth_samples_preserved']:,} \u4e2a\u91cd\u590d\u5b54\u6df1\u6837\u672c\u3002": "preserved {report['duplicate_depth_samples_preserved']:,} samples with duplicate depths.",
    '\u5df2\u9a8c\u8bc1 {len(trays)} \u4e2a\u6258\u76d8\u3001{len(sections)} \u4e2a\u884c\u6bb5\u3001{len(image_frames)} \u5f20\u56fe\u7247\u5173\u8054\u53ca\u8f6e\u5ed3\u5bf9\u5e94\u5173\u7cfb\u3002': "Verified {len(trays)} trays, {len(sections)} sections, {len(image_frames)} image associations, and profilometer correspondence.",
    '\u5149\u8c31\u77e9\u9635\u987a\u5e8f\u672a\u786e\u8ba4\uff0c\u672a\u751f\u6210\u5df2\u9a8c\u8bc1\u7684\u6837\u672c\u5149\u8c31\u5173\u8054\u3002\u672a\u751f\u6210\u771f\u5b9e\u4e09\u7ef4\u8f68\u8ff9\u6216\u50cf\u7d20\u5b54\u6df1\u6807\u5b9a\u3002': "Spectral matrix order is unconfirmed, so no validated sample-spectrum associations were generated. No true 3D trajectory or pixel-to-depth calibration was generated.",
    '# {hole} \u89c4\u8303\u8f7d\u8377': "# {hole} Canonical payloads",
    "\u751f\u6210\u5e76\u5168\u91cf\u56de\u8bfb\u9a8c\u8bc1 {len(assets)} \u4e2a Parquet \u6587\u4ef6\uff0c{report['canonical_bytes']:,} \u5b57\u8282\uff1b": "Generated and fully validated by readback {len(assets)} Parquet files, {report['canonical_bytes']:,} bytes; ",
    '\u6807\u91cf {scalar_rows_written:,} \u884c\u5168\u90e8\u4fdd\u7559\u3002': "all {scalar_rows_written:,} scalar rows were preserved.",
    '\u6570\u503c\u3001\u7c7b\u522b\u3001\u7a7a\u503c\u63a9\u7801\u3001\u539f\u59cb\u6807\u91cf\u6587\u672c\u548c\u6837\u672c\u987a\u5e8f\u5b8c\u6210\u9010\u6279\u6821\u9a8c\u3002': "Validated values, categories, null masks, original scalar text, and sample order batch by batch. ",
    '\u6e90 F32\u3001\u56fe\u7247\u53ca\u5143\u6570\u636e\u4fdd\u7559\u539f\u4ef6\u5f15\u7528\u4e0e\u54c8\u5e0c\uff0c\u6ca1\u6709\u91cd\u590d\u4e0b\u8f7d\u6216\u4e91\u7aef\u4e0a\u4f20\u3002': "Source F32 files, images, and metadata retain original references and hashes without repeated downloads or cloud uploads.",
    '\u5149\u8c31\u77e9\u9635\u987a\u5e8f\u4ecd\u672a\u786e\u8ba4\uff1b\u6ca1\u6709\u53d1\u5e03\u672a\u7ecf\u786e\u8ba4\u7684\u6837\u672c\u5149\u8c31\uff0c\u4e5f\u672a\u90e8\u7f72\u6570\u636e\u5e93\u3002': "Spectral matrix order remains unconfirmed; no unconfirmed sample spectra were published and no database was deployed.",
    '# \u672c\u6279\u5904\u7406\u9a8c\u8bc1\u7ed3\u679c': "# Batch processing verification results",
    '\u72b6\u6001\uff1a\u5df2\u901a\u8fc7\u5df2\u5b9e\u73b0\u5904\u7406\u8303\u56f4\u5185\u7684\u6821\u9a8c\uff0c\u4ecd\u6709\u660e\u786e\u7684\u80fd\u529b\u9650\u5236\u3002': "Status: checks passed within the implemented processing scope; stated capability limits remain.",
    '| \u94bb\u5b54 | \u6837\u672c | \u6807\u91cf\u884c | Parquet \u6587\u4ef6 | Parquet \u5b57\u8282 | \u4fdd\u7559\u7684\u91cd\u590d\u5b54\u6df1\u6837\u672c |': "| Borehole | Samples | Scalar rows | Parquet files | Parquet bytes | Preserved samples with duplicate depths |",
    "\u5408\u8ba1 {totals['source_file_count']} \u4e2a\u6765\u6e90\u6587\u4ef6\u3001{totals['scalar_log_count']} \u6761\u6807\u91cf\u65e5\u5fd7\u3001{totals['scalar_data_rows']:,} \u884c\u6807\u91cf\u6570\u636e\u3002": "Total: {totals['source_file_count']} source files, {totals['scalar_log_count']} scalar logs, and {totals['scalar_data_rows']:,} scalar rows.",
    '\u89c4\u8303\u8f7d\u8377\u6bcf\u6279\u503c\u4e0e\u7a7a\u503c\u63a9\u7801\u5df2\u7ecf\u8fc7\u56de\u8bfb\u6821\u9a8c\uff0c\u672c\u6b65\u9aa4\u53e6\u884c\u6838\u5bf9\u6587\u4ef6\u54c8\u5e0c\u3001\u7248\u672c\u4f9d\u8d56\u53ca\u6309\u5b54\u6df1\u8303\u56f4\u8bfb\u53d6\u3002\u91cd\u590d\u5b54\u6df1\u67e5\u8be2\u4fdd\u7559\u591a\u4e2a\u6837\u672c\u3002': "Values and null masks in canonical payloads have passed batch-by-batch readback checks. This step also checks file hashes, version dependencies, and depth-range reads. Queries at duplicate depths preserve all matching samples.",
    '\u4ecd\u672a\u5b9e\u73b0\uff1a\u5df2\u786e\u8ba4\u6392\u5217\u987a\u5e8f\u7684\u9010\u6837\u672c\u5149\u8c31\u3001\u771f\u5b9e\u4e09\u7ef4\u8f68\u8ff9\u3001\u6807\u5b9a\u540e\u7684\u5ca9\u5fc3\u8868\u9762\u3001\u53ef\u4fe1\u5ea6\u8bc4\u5206\u3001\u6570\u636e\u5e93\u5bfc\u5165\u548c\u4e91\u7aef\u4e0a\u4f20\u3002': "Outside this step: sample spectra with confirmed ordering, true 3D trajectories, calibrated core surfaces, confidence scores, database import, and cloud upload.",
    '\u6807\u91cf': "Scalar",
    '\u5149\u8c31': "Spectral",
    '\u8f6e\u5ed3': "Profilometer",
    '\u56fe\u7247': "Image",
}

def replace_text(value):
    for old, new in TEXT.items():
        value = value.replace(old, new)
    if re.search(r"[\u3400-\u9fff]", value):
        raise ValueError(f"Untranslated token: {value}")
    return value.translate(str.maketrans({"：": ": ", "。": ". ", "，": ", ", "；": "; ", "（": "(", "）": ")", "、": ", "}))

results = []
for path in FILES:
    baseline = ROOT / "_codex_work/english_code_20261003/before" / path.relative_to(ROOT)
    source = baseline.read_text(encoding="utf-8-sig")
    tree = ast.parse(source)
    doc_positions = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc is not None:
                item = node.body[0].value
                doc_positions[(item.lineno, item.col_offset)] = doc
    lines = source.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    replacements = []
    fstring_ranges = []
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            # AST columns use UTF-8 bytes, unlike tokenize columns.
            start_col = len(lines[node.lineno - 1].encode("utf-8")[:node.col_offset].decode("utf-8"))
            end_col = len(lines[node.end_lineno - 1].encode("utf-8")[:node.end_col_offset].decode("utf-8"))
            start = offsets[node.lineno - 1] + start_col
            end = offsets[node.end_lineno - 1] + end_col
            value = source[start:end]
            if re.search(r"[\u3400-\u9fff：。，；（）、]", value) and not any(a <= start and end <= b for a,b in fstring_ranges):
                fstring_ranges.append((start,end))
                replacements.append((start,end,replace_text(value)))
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        value = token.string
        token_start = offsets[token.start[0]-1] + token.start[1]
        if any(a <= token_start < b for a,b in fstring_ranges):
            continue
        if token.type == tokenize.COMMENT:
            chinese = value.removeprefix("#").strip()
            value = f"# {chinese} / {COMMENTS[chinese]}"
        elif token.start in doc_positions:
            chinese = doc_positions[token.start]
            indent = " " * token.start[1]
            value = f'"""{DOCS[chinese]}\n{indent}{chinese}\n{indent}"""'
        elif token.type == tokenize.STRING and re.search(r"[\u3400-\u9fff：。，；（）、]", value):
            value = replace_text(value)
        if value != token.string:
            replacements.append((offsets[token.start[0]-1] + token.start[1], offsets[token.end[0]-1] + token.end[1], value))
    for start, end, value in sorted(replacements, reverse=True):
        source = source[:start] + value + source[end:]
    source = source.replace("description=__doc__)", "description=__doc__.splitlines()[0])")
    ast.parse(source)
    path.write_text(source, encoding="utf-8", newline="\n")
    copy = ROOT / 'github-upload' / path.relative_to(ROOT)
    copy.write_bytes(path.read_bytes())
    results.append({"file": str(path.relative_to(ROOT)), "replacements": len(replacements)})
report = ROOT / "_codex_work/english_code_20261003/processing_translation.json"
report.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(results, ensure_ascii=False, indent=2))
