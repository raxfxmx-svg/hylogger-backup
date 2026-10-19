import ast
import io
import json
import shutil
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / '_codex_work/english_code_20261003'
NAMES = [p.name for p in (ROOT / 'github-upload/etl4/database').glob('*.py') if p.name[0].isdigit()]
NAMES += ['_final_import.py', '_media_common.py', '_media_import.py', '_media_manifest.py',
          '_media_reader.py', '_media_rows.py', '_media_verification.py', '_multi_common.py',
          '_multi_db.py', '_prepared_inputs.py', '_verification.py']

DOCS = {
    '\u660e\u786e\u5a92\u4f53\u5904\u7406\u7684\u6765\u6e90\u53d1\u5e03\uff0c\u6838\u5bf9\u5149\u8c31\u4e0e\u6587\u4ef6\u6e05\u5355\u3002': 'Select the source release for media processing and check spectra against the file manifest.',
    '\u7528\u7f13\u5b58\u7684\u5b98\u65b9\u6837\u672c\u8bb0\u5f55\u6838\u5bf9\u5149\u8c31\u6392\u5217\u548c\u6837\u672c\u53f7\u3002': 'Check spectral order and sample numbers against cached official sample records.',
    '\u4e3a\u539f\u59cb\u5149\u8c31\u5efa\u7acb\u5b57\u8282\u5757\u7d22\u5f15\uff0c\u4e0d\u590d\u5236\u5b8c\u6574\u6570\u7ec4\u3002': 'Index byte blocks in the original spectra without copying entire arrays.',
    '\u6309 dataset\u3001\u56fe\u7247\u65e5\u5fd7\u548c\u6258\u76d8\u5efa\u7acb\u56fe\u7247\u6e05\u5355\u3002': 'Build an image manifest by dataset, image log, and tray.',
    '\u6839\u636e\u884c\u6bb5\u4fe1\u606f\u63d0\u51fa\u88c1\u5207\u533a\u57df\uff0c\u751f\u6210\u4f9b\u68c0\u67e5\u7684\u62fc\u56fe\u3002': 'Propose crop regions from row sections and build contact sheets for review.',
    '\u68c0\u67e5\u884c\u95f4\u8fb9\u754c\uff0c\u4fdd\u7559\u5b8c\u6574\u5ca9\u5fc3\u50cf\u7d20\u5e76\u8bb0\u5f55\u4eba\u5de5\u5ba1\u9605\u7ed3\u679c\u3002': 'Check row boundaries, preserve all core pixels, and record visual review results.',
    '\u5c06\u56fe\u7247\u884c\u5173\u8054\u5230\u771f\u5b9e\u6837\u672c\u533a\u95f4\uff0c\u4fdd\u7559\u8fd1\u4f3c\u5b9a\u4f4d\u7684\u8bf4\u660e\u3002': 'Link image rows to actual sample intervals and retain the approximate-position explanation.',
    '\u751f\u6210\u65e0\u635f\u884c\u56fe\uff0c\u56de\u8bfb\u540e\u9010\u50cf\u7d20\u6838\u5bf9\u3002': 'Create lossless row images and compare every pixel after reading them back.',
    '\u540c\u4e00\u5f20\u539f\u56fe\u53ea\u89e3\u7801\u4e00\u6b21\uff0c\u8fd4\u56de\u6e05\u5355\u4ecd\u4fdd\u6301\u8f93\u5165\u884c\u987a\u5e8f\u3002': 'Decode each source image once and keep the returned rows in their input order.',
    '\u4fdd\u5b58\u4e00\u884c\u5e76\u56de\u8bfb\uff0c\u786e\u8ba4 PNG \u7f16\u7801\u6ca1\u6709\u6539\u53d8\u50cf\u7d20\u3002': 'Save and read back one row to confirm that PNG encoding preserves its pixels.',
    '\u5c01\u5b58\u5a92\u4f53\u51c6\u5907\u5305\u5e76\u5b8c\u6210\u7b2c\u4e00\u6b21\u672c\u5730\u9a8c\u6536\uff0c\u5b8c\u6574\u5165\u5e93\u7531\u6b65\u9aa4 37 \u6267\u884c\u3002': 'Seal the prepared media package and complete the first local acceptance; step 37 imports the full version.',
    '\u6838\u5bf9\u591a\u4e2a dataset \u7684\u65e5\u5fd7\u5f52\u5c5e\uff0c\u4f7f\u7528\u5df2\u4fdd\u5b58\u7684\u6765\u6e90\u8bc1\u636e\u3002': 'Check log membership across multiple datasets using saved source evidence.',
    '\u9010\u4e2a\u51c6\u5907 dataset\uff0c\u663e\u5f0f\u4f20\u5165\u89e3\u6790\u4e0a\u4e0b\u6587\u3002': 'Prepare each dataset with an explicitly supplied parsing context.',
    '\u6838\u5bf9\u591a dataset \u5149\u8c31\u5e76\u751f\u6210\u72ec\u7acb\u7684\u884c\u56fe\u8d44\u4ea7\u3002': 'Check spectra across multiple datasets and create separate row image assets.',
    '\u6309\u6765\u6e90\u6bb5\u6570\u627e\u884c\u8fb9\u754c\uff0c\u4fdd\u7559\u539f\u56fe\u7684\u95f4\u9699\u548c\u5168\u90e8\u50cf\u7d20\u3002': 'Find row boundaries from the source section count and preserve all image pixels and gaps.',
    '\u6bcf\u79cd\u5c3a\u5bf8\u548c\u884c\u6570\u5404\u53d6\u9996\u5c3e\u56fe\uff0c\u4f9b\u4eba\u5de5\u6838\u5bf9\u3002': 'Select the first and last images for each size and row count for visual review.',
    '\u4f7f\u7528\u6765\u6e90 section \u7684\u6837\u672c\u8303\u56f4\uff0c\u68c0\u67e5\u6bcf\u4e2a dataset \u7684\u8986\u76d6\u6570\u3002': 'Use source section sample ranges and check the coverage count for each dataset.',
    '\u6b63\u5f0f\u672c\u5730\u6279\u6b21\u5165\u53e3\uff1a\u8bfb\u53d6\u7b2c\u4e00\u6b21\u9a8c\u6536\u7684\u51c6\u5907\u5305\uff0c\u5b8c\u6574\u5165\u5e93\u5e76\u8fdb\u884c\u7b2c\u4e8c\u6b21\u9a8c\u6536\u3002': 'Import a complete local batch from packages that passed the first acceptance, then run the second acceptance.',
    '\u8ffd\u52a0\u65f6\u6cbf\u7528\u660e\u786e\u7684\u6765\u6e90\u53d1\u5e03\uff0c\u518d\u66ff\u6362\u672c\u6279\u6210\u5458\u3002': 'When appending, retain the explicit source release and replace the members in this batch.',
    '\u9a8c\u6536\u7ed3\u679c\u4e0e\u6570\u636e\u5728\u540c\u4e00\u4e8b\u52a1\u4e2d\u4fdd\u5b58\uff0c\u5931\u8d25\u65f6\u4e00\u8d77\u56de\u6eda\u3002': 'Save acceptance results and data in one transaction so that any failure rolls both back.',
    '\u5168\u90e8\u6210\u5458\u901a\u8fc7\u540e\uff0c\u518d\u63d0\u4ea4\u5c55\u793a\u7ec4\u5408\u548c\u53d1\u5e03\u6307\u9488\u3002': 'Commit display assemblies and the release pointer only after every member passes.',
    '\u8bfb\u53d6\u672c\u6279\uff0c\u9010\u4e2a\u5165\u5e93\u5e76\u9a8c\u6536\uff0c\u6700\u540e\u53d1\u5e03\u5e76\u4fdd\u5b58\u8fd0\u884c\u62a5\u544a\u3002': 'Read the batch, import and verify each dataset, then publish and save the run report.',
    '\u7b2c\u4e8c\u6b21\u672c\u5730\u9a8c\u6536\uff1a\u5931\u8d25\u7ed3\u679c\u4e0d\u80fd\u88ab\u540e\u7eed\u5bfc\u51fa\u5f53\u6210\u6210\u529f\u6279\u6b21\u3002': 'Run the second local acceptance and prevent failed batches from being exported as successful.',
    '\u767b\u8bb0\u672c\u6b21\u8f93\u5165\u6e05\u5355\uff0c\u51c6\u5907\u72ec\u7acb\u7684\u672c\u5730\u6570\u636e\u5e93\u5b9e\u4f8b\u3002': 'Register the selected input manifest and prepare an isolated local database instance.',
    '\u6309\u987a\u5e8f\u6267\u884c\u8fc1\u79fb\uff0c\u5e76\u8bbe\u7f6e\u5bfc\u5165\u548c\u8bfb\u53d6\u89d2\u8272\u7684\u6743\u9650\u3002': 'Apply migrations in order and grant permissions to the import and reader roles.',
    '\u6700\u7ec8\u7248\u672c\u7684\u8f93\u5165\u51c6\u5907\u3001\u5173\u8054 ID \u6620\u5c04\u548c\u5355 dataset \u5bfc\u5165\u3002': 'Prepare final-version inputs, map related IDs, and import individual datasets.',
    '\u8bfb\u53d6\u660e\u786e\u5217\u51fa\u7684\u5c01\u5b58\u5305\uff1b\u65e7\u5305\u901a\u8fc7\u6307\u5b9a\u5de5\u4f5c\u76ee\u5f55\u627e\u5230\u51c6\u5907\u6e05\u5355\u3002': 'Read explicitly listed sealed packages; locate older preparation manifests through the specified work directory.',
    '\u53ea\u66f4\u6362\u5185\u90e8\u5173\u8054 ID\uff1b\u6765\u6e90\u6587\u6863\u548c Parquet \u79d1\u5b66\u6570\u503c\u4fdd\u6301\u539f\u6837\u3002': 'Replace only internal relation IDs; preserve source documents and scientific values in Parquet files.',
    '\u8c03\u7528\u65b9\u6301\u6709\u4e8b\u52a1\uff1b\u53ea\u5199\u4e00\u4e2a\u5b8c\u6574\u7248\u672c\uff0c\u4e0d\u8c03\u7528\u57fa\u7840\u7248\u672c\u590d\u5236\u903b\u8f91\u3002': 'Use the transaction held by the caller to write one complete version without cloning a base version.',
    '\u56fe\u7247\u548c\u5149\u8c31\u6b65\u9aa4\u4f7f\u7528\u7684\u6587\u4ef6\u8bfb\u53d6\u4e0e\u5750\u6807\u8ba1\u7b97\u3002': 'Read files and calculate coordinates for image and spectral processing steps.',
    '\u6765\u6e90\u6bcf\u884c\u6309\u5b54\u6df1\u4ece\u5de6\u5230\u53f3\u6392\u5217\uff1b\u65e7\u53c2\u6570\u4ec5\u4fdd\u7559\u8bfb\u53d6\u517c\u5bb9\u3002': 'Source rows increase in depth from left to right; retain older arguments only for read compatibility.',
    '\u4e3a\u65b0\u6279\u6b21\u590d\u5236\u5c0f\u578b\u670d\u52a1\u683c\u5f0f\u4f9d\u636e\uff1b\u5149\u8c31\u548c\u56fe\u7247\u5927\u6587\u4ef6\u4ecd\u6309\u539f\u8def\u5f84\u8bfb\u53d6\u3002': 'Copy small service format references for a new batch; read large spectra and images from their original paths.',
    '\u5c01\u5b58\u5a92\u4f53\u51c6\u5907\u5305\u3001\u6267\u884c\u7b2c\u4e00\u6b21\u9a8c\u6536\uff0c\u5e76\u4e3a\u6700\u7ec8\u7248\u672c\u5199\u5165\u5a92\u4f53\u8bb0\u5f55\u3002': 'Seal prepared media packages, run the first acceptance, and write media records for the final version.',
    '\u8eab\u4efd\u53ea\u4f9d\u8d56\u8be5 dataset \u7684\u8f93\u5165\u548c\u89c4\u5219\uff1b\u5b9e\u9645\u8f93\u51fa\u53e6\u5b58\u6458\u8981\u3002': 'Derive identity only from dataset inputs and rules; store the actual output digest separately.',
    '\u4ece\u5305\u5185\u6e05\u5355\u91cd\u5efa\u57fa\u7840\u5bfc\u5165\u7684\u53c2\u6570\uff0c\u6587\u4ef6\u6309\u6e05\u5355\u5f15\u7528\u3002': 'Rebuild base import arguments from the package manifest and use its file references.',
    '\u5355\u3001\u591a dataset \u90fd\u4ece\u540c\u4e00\u4efd\u5305\u6e05\u5355\u53d6\u5f97\u51c6\u5907\u7ed3\u679c\u3002\u65e7\u5305\u53ea\u5728\u6b64\u8bfb\u53d6\u3002': 'Read prepared results for single or multiple datasets from the same manifest; handle older packages here.',
    '\u9a8c\u6536\u7ed1\u5b9a\u8f93\u5165\u5185\u5bb9\uff1b\u65f6\u95f4\u3001\u6e90\u7801\u548c\u672c\u673a\u76ee\u5f55\u4e0d\u51b3\u5b9a\u9a8c\u6536\u5bf9\u8c61\u3002': 'Bind acceptance to input content, independently of timestamps, source code, and local directories.',
    '\u7b2c\u4e00\u6b21\u672c\u5730\u9a8c\u6536\uff1a\u6c47\u603b\u5904\u7406\u68c0\u67e5\uff0c\u91cd\u65b0\u6838\u5bf9\u5b8c\u6574\u51c6\u5907\u5305\u53ca\u5176\u5f15\u7528\u3002': 'Run the first local acceptance by collecting processing checks and rechecking the complete package and its references.',
    '\u6838\u5bf9\u5305\u5185\u5a92\u4f53\u58f0\u660e\u4e0e\u57fa\u7840\u7248\u672c\u7684\u5b9e\u9645\u65e5\u5fd7\u3001\u56fe\u7247\u548c\u6837\u672c\u6765\u6e90\u3002': 'Check package media declarations against actual logs, images, and sample sources in the base version.',
    '\u6838\u5bf9\u672c\u6b21\u8f93\u5165\u5305\uff0c\u5e76\u6309 dataset \u6574\u7406\u540e\u7eed\u8981\u7528\u7684\u6e05\u5355\u3002': 'Check the selected input package and organize the required manifests by dataset.',
    '\u5411\u6307\u5b9a\u7248\u672c\u5199\u5a92\u4f53\u8bb0\u5f55\uff1b\u57fa\u7840\u8bb0\u5f55\u7531\u8c03\u7528\u65b9\u5728\u540c\u4e00\u4e8b\u52a1\u5185\u51c6\u5907\u3002': 'Write media records into the specified version; the caller prepares base records in the same transaction.',
    '\u5a92\u4f53\u6e05\u5355\u53ea\u4fdd\u5b58\u4e00\u4efd\u516c\u5171\u4fe1\u606f\uff1b\u8bfb\u53d6\u65f6\u8fd8\u539f\u4e3a\u5404\u6b65\u9aa4\u4f7f\u7528\u7684\u5b57\u5178\u3002': 'Store shared media metadata once and expand it into the dictionaries used by each processing step.',
    '\u6309 dataset\u3001\u6837\u672c\u8f74\u548c\u6837\u672c\u53f7\u8bfb\u53d6\u7ed3\u679c\u53ca\u5a92\u4f53\u3002': 'Read results and media by dataset, sample axis, and sample number.',
    '\u4e00\u6b21\u67e5\u8be2\u672c\u6b21\u7528\u5230\u7684\u8d44\u4ea7\uff0c\u4ecd\u6309\u4f4d\u7f6e\u987a\u5e8f\u9009\u62e9\u53ef\u7528\u7684\u672c\u5730\u6587\u4ef6\u3002': 'Fetch the needed assets in one query and select available local files in location order.',
    '\u6309\u672c\u6b21\u9009\u4e2d\u7684\u65e5\u5fd7\u6279\u91cf\u8bfb\u53d6\u7d22\u5f15\uff0c\u4e0d\u7f13\u5b58\u8de8\u8bf7\u6c42\u7684\u6570\u636e\u5e93\u72b6\u6001\u3002': 'Fetch indexes for the selected logs in batches without caching database state across requests.',
    '\u5165\u5e93\u4e8b\u52a1\u5185\u9a8c\u6536\u5c1a\u672a\u53d1\u5e03\u7684\u5b8c\u6574\u7248\u672c\uff0c\u4ecd\u6838\u5bf9\u7248\u672c\u3001dataset \u548c\u6837\u672c\u8f74\u3002': 'Verify the unpublished complete version within the import transaction, including its version, dataset, and sample axis.',
    '\u5355 dataset \u548c\u591a dataset \u5171\u7528\u7684\u56fe\u7247\u884c\u8fb9\u754c\u3001\u6837\u672c\u5173\u8054\u7b97\u6cd5\u3002': 'Share image row boundary and sample association algorithms across single and multiple datasets.',
    '\u5728\u9884\u8ba1\u884c\u95f4\u4f4d\u7f6e\u5bfb\u627e\u4eae\u5ea6\u5206\u9694\u7ebf\uff0c\u4e0d\u660e\u663e\u65f6\u6309\u7b49\u9ad8\u6a21\u677f\u5212\u5206\u3002': 'Look for bright dividers near expected row boundaries and use equal-height rows when dividers are unclear.',
    '\u4f7f\u7528\u6765\u6e90 section \u7684\u8f74\u3001\u6258\u76d8\u548c\u6837\u672c\u8303\u56f4\uff0c\u4e0d\u6309\u6df1\u5ea6\u53bb\u91cd\u3002': 'Use the source section axis, tray, and sample range without deduplicating depths.',
    '\u9010\u6837\u672c\u6838\u5bf9\u57fa\u7840\u6570\u503c\uff0c\u5e76\u68c0\u67e5\u5a92\u4f53\u6765\u6e90\u548c\u8bfb\u53d6\u7ed3\u679c\u3002': 'Compare base values sample by sample and check media sources and reader results.',
    '\u72ec\u7acb\u8bfb\u53d6\u671f\u671b\u503c\uff0c\u6bcf\u4e2a\u9700\u8981\u7684\u884c\u7ec4\u53ea\u8bfb\u4e00\u6b21\u3002': 'Read expected values independently and read each required row group only once.',
    '\u540c\u4e00\u539f\u56fe\u53ea\u89e3\u7801\u4e00\u6b21\uff0c\u4ecd\u9010\u5f20\u68c0\u67e5\u88c1\u56fe\u7684\u6570\u636e\u5e93\u6765\u6e90\u548c\u50cf\u7d20\u3002': 'Decode each source image once while checking every crop against its database source and pixels.',
    '\u591a dataset \u7684\u660e\u786e\u6765\u6e90\u8303\u56f4\u548c\u51c6\u5907\u7ed3\u679c\u8bfb\u53d6\u3002': 'Read the explicit source scope and prepared results for multiple datasets.',
    '\u8bb0\u5f55\u6765\u6e90\u53d1\u5e03\uff0c\u5e76\u5efa\u7acb\u53ef\u8ffd\u6eaf\u7684\u5c55\u793a\u53d6\u6bb5\u3002': 'Record the source release and build traceable display segments.',
    '\u53ea\u6bd4\u8f83\u5df2\u5b58\u8bb0\u5f55\uff1b\u7f3a\u5931\u6216\u4e0d\u4e00\u81f4\u90fd\u62a5\u9519\uff0c\u4e0d\u8865\u5efa\u3002': 'Compare existing records only and reject missing or inconsistent records without creating replacements.',
    '\u9a8c\u6536\u5c55\u793a\u53d6\u6bb5\uff0c\u4e0d\u4fee\u6539\u6570\u636e\u5e93\u8bb0\u5f55\u3002': 'Verify display segments without changing database records.',
    '\u8bfb\u53d6\u672c\u6b21\u9009\u5b9a\u7684\u51c6\u5907\u6e05\u5355\uff0c\u5e76\u6838\u5bf9\u5f15\u7528\u7684\u6587\u4ef6\u3002': 'Read the selected preparation manifest and check its file references.',
    '\u4ee5\u672c\u6b21\u9a8c\u8bc1\u6e05\u5355\u786e\u5b9a\u8303\u56f4\uff0c\u5b54\u53f7\u548c\u6bcf\u5b54\u7ed3\u679c\u5fc5\u987b\u4e00\u4e00\u5bf9\u5e94\u3002': 'Use the selected verification manifest as the scope and require one result for each hole ID.',
    '\u6700\u7ec8\u5165\u5e93\u53ef\u4f20\u5165\u5df2\u6362\u597d\u5185\u90e8 ID \u7684\u6587\u6863\uff0c\u6765\u6e90\u6587\u4ef6\u4ecd\u4fdd\u6301\u539f\u6837\u3002': 'Allow final imports to supply documents with remapped internal IDs while preserving source files.',
    '\u6838\u5bf9\u5355\u4e2a dataset \u7684\u5143\u6570\u636e\u3001\u6837\u672c\u548c\u8d44\u4ea7\uff1b\u4e0d\u8d1f\u8d23\u53d1\u5e03\u6216\u63a5\u53e3\u68c0\u67e5\u3002': 'Check metadata, samples, and assets for one dataset without publishing or checking APIs.',
}
COMMENTS = {
    '\u8fd9\u91cc\u63a5\u6536\u5355 dataset \u51c6\u5907\u7ed3\u679c\uff1b\u591a dataset \u4f7f\u7528\u5404\u81ea\u7684\u4e0a\u4e0b\u6587\u3002': 'Accept prepared results for a single dataset here; multiple datasets use separate contexts.',
    '\u628a JSON \u5c0f\u6570\u8fd8\u539f\u4e3a float32 \u540e\u9010\u4f4d\u6bd4\u8f83\uff0c\u4fdd\u7559\u96f6\u548c\u975e\u6709\u9650\u503c\u3002': 'Restore JSON decimals to float32 for bitwise comparison, preserving zeros and nonfinite values.',
    '\u6bcf\u79cd\u94bb\u5b54\u3001\u5c3a\u5bf8\u548c\u884c\u6570\u9009\u53d6\u9996\u5c3e\u56fe\u3002': 'Select the first and last images for each hole, image size, and row count.',
    '\u5171\u4eab\u6e05\u5355\u7684\u5176\u4ed6 dataset \u53d8\u5316\uff0c\u4e0d\u5c5e\u4e8e\u672c dataset \u7684\u6570\u636e\u8eab\u4efd\u3002': 'Changes to other datasets in a shared manifest do not affect this dataset identity.',
    '\u5c0f\u578b\u6765\u6e90\u6587\u6863\u968f\u7248\u672c\u5c01\u5b58\uff0c\u65e7\u7248\u672c\u4e0d\u518d\u5f15\u7528\u4f1a\u66f4\u65b0\u7684\u6574\u5b54\u6e05\u5355\u3002': 'Seal small source documents with each version so older versions do not reference changing hole manifests.',
    '\u6700\u65b0\u6e05\u5355\u53ef\u91cd\u5efa\uff1b\u6b64\u65f6\u4ecd\u6301\u6709\u5bfc\u5165\u9501\uff0c\u907f\u514d\u8986\u76d6\u53e6\u4e00\u6279\u7684\u5165\u53e3\u3002': 'The latest manifest can be rebuilt; keep the import lock to avoid overwriting another batch entry.',
    '\u6b65\u9aa4 6 \u5df2\u9a8c\u8bc1\u4ea7\u7269\uff1b\u8fd9\u91cc\u767b\u8bb0\u6458\u8981\uff0c\u6b65\u9aa4 28 \u548c 37 \u5728\u9a8c\u6536\u8fb9\u754c\u91cd\u65b0\u6838\u9a8c\u3002': 'Step 6 already checked the outputs; register their digests here and recheck them at acceptance in steps 28 and 37.',
    '\u4fdd\u7559\u5de5\u4f5c\u76ee\u5f55\u7ee7\u627f\u7684\u6743\u9650\uff0c\u907f\u514d\u5f53\u524d\u6267\u884c\u73af\u5883\u5931\u53bb\u8bbf\u95ee\u6743\u9650\u3002': 'Preserve inherited work directory permissions so the current environment retains access.',
    'Windows \u8fd4\u56de\u7684\u6b64\u8def\u5f84\u4f7f\u7528\u7cfb\u7edf\u4ee3\u7801\u9875\u3002': 'Windows returns this path using the system code page.',
    '\u5a92\u4f53\u7248\u672c\u590d\u5236\u4f7f\u7528\u4f1a\u8bdd\u5185\u7684 UUID \u5bf9\u7167\u8868\u3002': 'Media version cloning uses a UUID mapping table scoped to the session.',
    'NVCL \u539f\u59cb JSON \u662f\u6765\u6e90\u8bc1\u636e\uff0c\u4e0d\u80fd\u628a\u5176\u4e2d\u7684\u6807\u8bc6\u6539\u6210\u5185\u90e8\u6807\u8bc6\u3002': 'Original NVCL JSON is source evidence; do not replace its identifiers with internal IDs.',
    '\u88c1\u56fe\u4f7f\u7528\u89e3\u7801\u540e\u7684\u539f\u59cb\u5750\u6807\uff1b\u62d2\u7edd\u672a\u7ecf\u5ba1\u9605\u7684 EXIF \u53d8\u6362\u3002': 'Crop using decoded native coordinates and reject EXIF transformations that have not been reviewed.',
    '\u952e\u4e3a\u6765\u6e90 dataset ID\uff0c\u53ea\u8986\u76d6\u53d7\u5f71\u54cd\u7684\u5904\u7406\u89c4\u5219\u3002': 'Key overrides by source dataset ID and change only the affected processing rules.',
    '\u672a\u5355\u72ec\u8986\u76d6\u65f6\uff0c\u4ecd\u6309\u5305\u5185\u4fdd\u5b58\u7684\u5171\u540c\u89c4\u5219\u590d\u67e5\u5386\u53f2\u7248\u672c\u3002': 'Without an individual override, recheck historical versions using the shared rules saved in the package.',
    '\u5c01\u5b58\u540e\u7684\u5f15\u7528\u6307\u5411\u5305\u5185\u8bc1\u636e\uff0c\u4e0d\u4f9d\u8d56\u51c6\u5907\u65f6\u7684\u4e34\u65f6\u76ee\u5f55\u3002': 'Sealed references point to evidence inside the package without relying on temporary preparation directories.',
    '\u8bc1\u636e\u6587\u4ef6\u53ef\u5171\u7528\uff0c\u8d44\u4ea7\u8bb0\u5f55\u4ecd\u5f52\u5c5e\u4e8e\u5404\u81ea\u7684\u6570\u636e\u7248\u672c\u3002': 'Evidence files may be shared, but asset records still belong to their respective data versions.',
    '\u53ea\u63d0\u53d6\u6bcf\u9879\u90fd\u6709\u4e14\u503c\u5b8c\u5168\u76f8\u540c\u7684\u5b57\u6bb5\uff0c\u884c\u9ad8\u7b49\u5dee\u5f02\u4ecd\u7559\u5728\u539f\u4f4d\u3002': 'Extract only fields present and identical in every item; keep differences such as row height on each item.',
    'frames \u5217\u8868\u4fdd\u7559 id \u4f5c\u4e3a\u5f15\u7528\uff1brows \u5217\u8868\u4fdd\u7559 source_frame_id\u3002': 'Keep id as the reference in frames and source_frame_id as the reference in rows.',
    '\u65e7\u5c01\u5b58\u5305\u4fdd\u6301\u539f\u6837\uff0c\u4e0d\u6539\u5199\u6587\u4ef6\u6216\u65e7\u6307\u7eb9\u3002': 'Preserve older sealed packages without rewriting files or their fingerprints.',
    '\u591a\u5f20\u5019\u9009\u56fe\u7247\u660e\u786e\u8fd4\u56de\uff0c\u7531\u8c03\u7528\u8005\u9009\u62e9\u65e5\u5fd7\u3002': 'Return all candidate images explicitly and let the caller select a log.',
    '\u6838\u5bf9\u590d\u7528\u7684 Parquet \u548c\u65b0\u589e\u884c\u56fe\u7684\u5b9e\u9645\u6587\u4ef6\u3002': 'Check the actual files for reused Parquet assets and newly created row images.',
    '\u8bfb\u53d6\u65f6\u4fdd\u7559\u89e3\u91ca\u7ed3\u679c\u7684\u7b97\u6cd5\u53d8\u4f53\u548c\u539f\u59cb\u503c\u3002': 'Preserve interpretation algorithm variants and original values when reading results.',
    '\u8fb9\u754c\u5e38\u4e3a\u7a7a\u503c\uff0c\u53e6\u9009\u6709\u77ff\u7269\u540d\u79f0\u548c\u6743\u91cd\u7684\u6837\u672c\u6838\u5bf9\u3002': 'Boundary values are often null; also check samples with mineral names and weights.',
    '\u5c06\u5b98\u65b9\u6837\u672c\u4e0e\u79bb\u7ebf\u8bfb\u53d6\u7ed3\u679c\u6309 float32 \u6bd4\u8f83\u3002': 'Compare official samples and offline reader results as float32 values.',
}
RUNTIME = {
    '\u4ece\u6587\u4ef6\u51c6\u5907\u6700\u7ec8\u7248\u672c\uff0c\u4e0d\u8981\u6c42\u57fa\u7840\u7248\u672c\u5148\u5165\u5e93': 'Prepare the final version from files without importing a base version first',
    '\u663e\u5f0f\u5f15\u7528\u5df2\u6709\u51c6\u5907\u6587\u4ef6\u6240\u5728\u5de5\u4f5c\u76ee\u5f55': 'Explicit work directory containing existing prepared files',
    '\u6587\u4ef6\u51c6\u5907\u4e0e\u6765\u6e90\u53d1\u5e03\u4e0d\u80fd\u540c\u65f6\u6307\u5b9a': 'File preparation and a source release cannot be selected together',
    '\u4fdd\u7559\u539f\u56fe\u884c\u5185\u50cf\u7d20\u3001\u5206\u9694\u7ebf\u548c\u7a7a\u6bb5\uff1b\u6309\u6765\u6e90\u89c4\u8303\u4ece\u5de6\u5230\u53f3\u589e\u52a0\u5b54\u6df1\u3002': 'Preserve original row pixels, dividers, and empty sections; depth increases from left to right according to the source specification.',
    '\u5df2\u6709\u5c01\u5b58\u5305\u76ee\u5f55\uff0c\u652f\u6301\u8131\u79bb\u5a92\u4f53\u5de5\u4f5c\u76ee\u5f55\u590d\u8dd1': 'Existing sealed package directory; supports reruns without the media work directory',
    '\u517c\u5bb9\u539f\u547d\u4ee4\uff1b\u672c\u6b65\u9aa4\u9ed8\u8ba4\u53ea\u5c01\u5b58\u5e76\u9a8c\u6536\uff0c\u968f\u540e\u4f7f\u7528\u6b65\u9aa4 37': 'Compatibility flag; this step seals and verifies packages by default, then use step 37',
    '\u65e7\u5305\u7684\u51c6\u5907\u5de5\u4f5c\u76ee\u5f55\uff1b\u65b0\u6279\u6b21\u4f7f\u7528\u540c\u4e00 --work-dir': 'Preparation work directory for older packages; new batches share --work-dir',
    '\u5a92\u4f53\u6b65\u9aa4\u76ee\u5f55\uff0c\u591a dataset \u53ef\u6307\u5b9a multi_work/media': 'Media step directory; use multi_work/media for multiple datasets',
    '\u5a92\u4f53\u8bc1\u636e\u76ee\u5f55\uff0c\u591a dataset \u53ef\u6307\u5b9a multi_work/evidence': 'Media evidence directory; use multi_work/evidence for multiple datasets',
    '\u7b2c\u4e00\u6b21\u672c\u5730\u9a8c\u6536\u901a\u8fc7\uff1a{package_path}\uff1b\u4e0b\u4e00\u6b65\u8fd0\u884c 37 \u5b8c\u6574\u5165\u5e93\u3002': 'First local acceptance passed: {package_path}; run step 37 next to import the full version.',
    '# \u591a dataset \u6765\u6e90\u6838\u67e5': '# Multiple dataset source audit',
    '| \u5b54 | dataset | \u6837\u672c\u6570 | \u6df1\u5ea6\u8303\u56f4 m | \u6258\u76d8\u6570 |': '| Hole | Dataset | Samples | Depth range (m) | Trays |',
    '\u65e5\u5fd7\u5f52\u5c5e\u4f9d\u636e\uff1a\u5b98\u65b9\u6309 dataset \u67e5\u8be2\u7684\u6807\u91cf/\u5149\u8c31\u65e5\u5fd7 ID \u4e0e\u539f\u59cb\u5305\u9010\u9879\u4ea4\u96c6\u6838\u5bf9\uff1b\u56fe\u7247\u4f7f\u7528\u539f\u59cb\u663e\u5f0f dataset_id\uff1b\u8f6e\u5ed3\u9700\u5728\u6b65\u9aa4 32 \u5b8c\u6210\u5168\u91cf prof_min \u5bf9\u7167\u3002': 'Log membership evidence: intersect official scalar and spectral log IDs queried by dataset with each original package; use explicit source dataset_id values for images; compare all prof_min values for profiles in step 32.',
    '\u63a5\u66ff\u5173\u7cfb\u4e0d\u80fd\u7531\u6b64\u8868\u7684\u6392\u5217\u63a8\u65ad\uff0c\u53e6\u884c\u8bb0\u5f55\u7528\u6237\u786e\u8ba4\u3002': 'Do not infer succession relationships from the table order; record user confirmation separately.',
    '\u6240\u9009\u5b54\u4e0d\u5728\u6b65\u9aa4 31 \u7684\u6e05\u5355\u4e2d': 'Selected holes are not in the step 31 manifest',
    '\u589e\u91cf\u6279\u6b21\u7684\u6765\u6e90\u53d1\u5e03\u5df2\u6539\u53d8': 'The source release for the incremental batch has changed',
    '\u6700\u7ec8\u7248\u672c\u5df2\u63d0\u4ea4\uff1b\u6700\u65b0\u6e05\u5355\u5165\u53e3\u5f85\u91cd\u5efa\uff1a{type(error).__name__}': 'Final version committed; the latest manifest entry needs rebuilding: {type(error).__name__}',
    '\u8bf7\u4f7f\u7528\u660e\u786e\u9009\u5b9a\u7684\u672c\u5730\u6279\u6b21\u5e93\uff0c\u4e0d\u80fd\u8986\u76d6\u65e7\u4ea4\u4ed8\u5e93': 'Use an explicitly selected local batch database; do not overwrite the previous delivery database',
    '\u53e6\u4e00\u4e2a\u5bfc\u5165\u6216\u9a8c\u6536\u6b63\u5728\u8fd0\u884c': 'Another import or acceptance is running',
    "\u5bfc\u5165\u5e76\u9a8c\u6536 {item['unit']['hole_id']} / {item['unit']['source_dataset_id']}": "Importing and verifying {item['unit']['hole_id']} / {item['unit']['source_dataset_id']}",
    '\u5305\u8def\u5f84\u3001\u51c6\u5907\u76ee\u5f55\u548c\u591a dataset \u53d6\u6bb5\u51b3\u7b56': 'Package paths, preparation directories, and segment decisions for multiple datasets',
    "\u6700\u7ec8\u53d1\u5e03\uff1a{result['release_id']}\uff1b\u672c\u6279 {len(result['datasets'])} \u4e2a dataset": "Final release: {result['release_id']}; {len(result['datasets'])} datasets in this batch",
    '\u5df2\u9009\u62e9\u73b0\u6709\u5b9e\u4f8b\u914d\u7f6e\uff1b\u767b\u8bb0\u8f93\u5165\u8bf7\u4f7f\u7528 --inputs-only\uff0c\u5b9e\u4f8b\u542f\u505c\u8bf7\u5728\u539f\u8fd0\u884c\u76ee\u5f55\u6267\u884c': 'An existing instance configuration is selected; use --inputs-only to register inputs and start or stop the instance from its original runtime directory',
    '\u53ea\u6838\u5bf9\u8f93\u5165\uff1b\u4f7f\u7528\u5df2\u914d\u7f6e\u7684\u6570\u636e\u5e93\u5b9e\u4f8b': 'Check inputs only and use the configured database instance',
    '--inputs-only \u4e0d\u80fd\u4e0e --runtime-only \u6216 --stop \u540c\u65f6\u4f7f\u7528': '--inputs-only cannot be combined with --runtime-only or --stop',
    '\u6279\u6b21\u6ca1\u6709\u8f93\u5165\u5305': 'The batch has no input packages',
    '\u7f3a\u5c11\u7b2c\u4e00\u6b21\u672c\u5730\u9a8c\u6536\uff0c\u8bf7\u5148\u8fd0\u884c\u6b65\u9aa4 28 --package-only': 'First local acceptance is missing; run step 28 --package-only first',
    '\u7b2c\u4e00\u6b21\u672c\u5730\u9a8c\u6536\u4e0e\u5f53\u524d\u8f93\u5165\u4e0d\u4e00\u81f4\uff0c\u8bf7\u91cd\u65b0\u6267\u884c\u6b65\u9aa4 28 --package-only': 'First local acceptance does not match the current inputs; rerun step 28 --package-only',
    '\u540c\u4e00\u6279\u6b21\u91cd\u590d\u5305\u542b dataset': 'The batch contains a duplicate dataset',
    '\u5904\u7406\u89c4\u5219\u7248\u672c\u4e0d\u80fd\u4e3a\u7a7a': 'The processing rule version must not be empty',
    '\u89c4\u5219\u7248\u672c\u8986\u76d6\u5305\u542b\u672c\u6279\u6b21\u4ee5\u5916\u7684 dataset': 'Rule version overrides include datasets outside this batch',
    '\u5305\u5185 dataset \u4e0d\u5728\u51c6\u5907\u6e05\u5355\u4e2d': 'A package dataset is not in the preparation manifest',
    '\u5a92\u4f53\u5305\u4e0e\u51c6\u5907\u6587\u4ef6\u7684 dataset\u3001\u7248\u672c\u6216\u6837\u672c\u8f74\u4e0d\u4e00\u81f4': 'The media package and prepared files differ in dataset, version, or sample axis',
    '\u5a92\u4f53\u6b65\u9aa4 {number} \u4e0d\u5728\u5c01\u5b58\u6e05\u5355\u4e2d': 'Media step {number} is not in the sealed manifest',
    '\u5a92\u4f53\u6b65\u9aa4 {number} \u672a\u5b8c\u6210': 'Media step {number} is incomplete',
    '\u51c6\u5907\u62a5\u544a\u672a\u901a\u8fc7\u6216\u6df7\u7528\u4e86\u8f93\u5165\uff1a{name}': 'The preparation report failed or combines different inputs: {name}',
    '\u51c6\u5907\u62a5\u544a\u4e0d\u5728\u9a8c\u6536\u6e05\u5355\u4e2d\uff1a{name}': 'The preparation report is not in the acceptance manifest: {name}',
    '\u539f\u59cb\u6587\u4ef6\u4e0e\u51c6\u5907\u7ed3\u679c\u4e0d\u4e00\u81f4': 'Raw files do not match the prepared results',
    '\u51c6\u5907\u6e05\u5355\u7f3a\u5c11\u5fc5\u8981\u4ea7\u7269': 'The preparation manifest is missing required outputs',
    '\u51c6\u5907\u4ea7\u7269\u4e0e\u5b58\u50a8\u6e05\u5355\u4e0d\u4e00\u81f4': 'Prepared outputs do not match the storage manifest',
    '\u6307\u793a\u7ebf\u6309\u6837\u672c\u5e8f\u53f7\u4f30\u7b97\u4f4d\u7f6e\uff1b\u6df1\u5ea6\u4e0e\u7ed3\u679c\u6765\u81ea\u6240\u9009\u6837\u672c\u3002': 'The indicator position is estimated from the sample number; depth and results come from the selected sample.',
    '\u76f8\u90bb\u56fe\u7247\u884c\u7684\u8fb9\u754c\u6837\u672c\u4e0e\u5b9a\u4f4d\u4e0d\u4e00\u81f4': 'Boundary samples and positions are inconsistent between adjacent image rows',
    '\u591a dataset \u6d41\u7a0b\u8981\u6c42\u4e00\u4e2a\u5b54\u5305\u542b\u591a\u4e2a dataset': 'The multiple dataset workflow requires more than one dataset in a hole',
}


def docstrings(tree):
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.body and isinstance(node.body[0], ast.Expr):
                value = node.body[0].value
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    yield value


results = []
for name in NAMES:
    source = ROOT / 'etl4/database' / name
    before = WORK / 'before/etl4/database' / name
    if not before.exists():
        before.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, before)
    original = source.read_text(encoding='utf-8-sig')
    lines = original.splitlines(keepends=True)
    edits = []
    for doc in docstrings(ast.parse(original)):
        assert doc.value in DOCS, (name, doc.value)
        assert doc.lineno == doc.end_lineno
        indent = ' ' * doc.col_offset
        replacement = indent + '"""' + DOCS[doc.value] + '\n' + indent + doc.value + '\n' + indent + '"""\n'
        edits.append((doc.lineno - 1, replacement))
    for tok in tokenize.generate_tokens(io.StringIO(original).readline):
        if tok.type == tokenize.COMMENT:
            chinese = tok.string.removeprefix('#').strip()
            assert chinese in COMMENTS, (name, chinese)
            line = lines[tok.start[0] - 1]
            replacement = line[:tok.start[1]] + '# ' + chinese + ' / ' + COMMENTS[chinese] + '\n'
            edits.append((tok.start[0] - 1, replacement))
    for line, replacement in sorted(edits, reverse=True):
        lines[line] = replacement
    updated = ''.join(lines)
    used = []
    for chinese, english in RUNTIME.items():
        if chinese in updated:
            updated = updated.replace(chinese, english)
            used.append(chinese)
    updated = updated.replace('description=__doc__', 'description=__doc__.splitlines()[0]')
    ast.parse(updated)
    source.write_text(updated, encoding='utf-8', newline='\n')
    shutil.copyfile(source, ROOT / 'github-upload/etl4/database' / name)
    results.append({'file': name, 'docstrings_and_comments': len(edits), 'runtime_translations': len(used)})
(WORK / 'media_translation_changes.json').write_text(json.dumps(results, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'files': len(results), 'docstrings_and_comments': sum(x['docstrings_and_comments'] for x in results),
                  'runtime_translations': sum(x['runtime_translations'] for x in results)}))
