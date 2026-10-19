# Dataset selection and borehole identity

Project decisions recorded on 2026-10-11. These rules resolve the earlier
cuttings and same-name borehole deferrals. External handlers
[12](../special_processing/12_core_only/README.md) and
[13](../special_processing/13_split_boreholes/README.md) implement input preparation.

## 1. Keep core; exclude cuttings

This project analyses cored intervals only. Remove cuttings datasets from the
selected processing inputs and final delivery. Retain the core datasets and
run the usual preparation checks on them.

For this retrospective study, cuttings are no longer used as evidence for
drilling decisions. They can still provide continuous evidence for lithological,
mineralogical and stratigraphic correlation. Where core is available:

> Use core to calibrate and cuttings to extrapolate. Core provides ground truth;
> cuttings provide continuity.

Because this project covers only cored intervals, cuttings can be omitted.
Their exclusion is a scope decision, not a finding that the data are defective.

Apply the decision as follows:

- Identify cuttings from the source dataset labels or metadata, including labels
  such as `cuttings` and `cuttings2`. Do not discard a whole hole because one of
  its datasets contains cuttings.
- Exclude the cuttings datasets and their dataset-specific records and assets
  from prepared packages, import and publication. Keep assets used by retained
  core datasets. Do not join cuttings onto a core depth axis or use them to fill gaps.
- Record excluded dataset IDs with the reason `out_of_scope_cuttings`.
  If no core dataset remains, omit that hole from this project's delivery.
  Unclear sample types require review rather than automatic deletion.

This applies to Abbarwardoo 1, Allanooka 1, Apium 1, Arrowsmith 2, Barnicarndy 1,
Beharra Springs 2, Beharra Springs North 1 and Blina 1. It also applies to
Tamala 1_cuttings and Tamala 1_cuttings2 in future project deliveries; their
earlier test results remain historical evidence.

## 2. Split same-name boreholes by source

Treat the reviewed same-name/different-source cases as separate boreholes.
Use this working and published name:

```text
<original-hole-name>-<source-name>
```

Use the source project name as the distinguishing label. If it is empty or
missing, use `unnamed`. Use an ordinary hyphen (`-`) as the separator.
For the reviewed BBDD0001 and BBDD0002 sources, the approved short label for
`Lake Roe - Bombara Prospect` is `Lake Roe-Bombara`. Retain the full original
project text in provenance.

Examples:

- `BBDD0001` from Bannockburn becomes `BBDD0001-Bannockburn`.
- `BBDD0001` from Lake Roe - Bombara Prospect becomes `BBDD0001-Lake Roe-Bombara`.
- `BH01` from Behemoth becomes `BH01-Behemoth`.
- `BH01` with no project name becomes `BH01-unnamed`.

The current five groups are:

| Original hole name | Separate borehole names |
|---|---|
| BBDD0001 | `BBDD0001-Bannockburn`; `BBDD0001-Lake Roe-Bombara` |
| BBDD0002 | `BBDD0002-Bannockburn`; `BBDD0002-Lake Roe-Bombara` |
| BH01 | `BH01-Behemoth`; `BH01-unnamed` |
| BH02 | `BH02-Behemoth`; `BH02-unnamed` |
| BNDD001 | `BNDD001-Stanley`; `BNDD001-Binneringie` |

Keep each resulting borehole's samples, coordinates, logs, images and spectra
with its own source datasets. Do not concatenate depth axes or merge records
merely because the original hole name is identical.

Preserve original dataset IDs, source names, project text and borehole URIs as
provenance. Record the mapping to the new borehole name. Renaming a folder alone
does not perform this split. If two sources still produce the same name,
including two unnamed sources, stop for a naming decision rather than overwrite
or merge them.

## Implementation boundary

Implement these operations outside the original `etl4/`. Prepare the selected
core datasets and separated borehole inputs, then run the existing checks.
Cases 12 and 13 prepare independent raw packages from diagnosed failures. They
use the cached official dataset response to select logs and verify copied
payload hashes. The automatic failure entry then runs normal preparation and
retries supported special cases. Case 13 reads each dataset's coordinates without
requiring a manual collar file. By the project owner's decision, the source
coordinates are treated as sharing the project's EPSG:4326 system and are used
unchanged. The source datum and the assumption are preserved. Unknown optional
company, dates and hole length remain null and do not block preparation.
Case 01 or case 11 alone does not filter cuttings or split borehole identities.

This document update does not delete archived raw files, modify an existing
database or rename existing deliveries. Those actions have not been performed.
