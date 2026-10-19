# Historical special cases

Reviewed on 2026-10-11. This records earlier failures and handling methods.
Use [Special processing](../special_processing/README.md) for current commands.
The original `etl4/` is unchanged; external handlers implement the input cases.
Historical success does not automatically approve a new source with a similar name.

## Cases and handling

Historical IDs S01–S16 differ from the executable folder numbers below.
Counts overlap because one hole can have several issues.

| History ID | Failure and reviewed handling | Executable folder |
|---|---|---|
| S01 | Spaces, encoded names or extra identity files fail the old entry. Accept safe single-component names after checking decoded hole, directory, package and provider identities; preserve source IDs and hashes. Reject traversal, reserved names and conflicting identities. | [01](../special_processing/01_source_identity/README.md) |
| S02 | 05GJD001 explicitly has no profile. Preserve metadata without inventing a payload; require consistent unavailable status, zero counts, no hash and no actual file. | [10](../special_processing/10_unavailable_profile/README.md) |
| S03 | virtual_section restarts in each tray. Compare every sample with numbering derived from complete Tray/Section intervals; retain original and global labels. The historical register has 53 datasets. | [02](../special_processing/02_tray_local_sections/README.md) |
| S04 | Some auxiliary labels are null. Preserve them and require every available value to match. 15RCDVZ001 has 15,319 nulls of 61,881 samples; BM5346 has 3,577 of 10,800. Both had zero non-null mismatches. | [05](../special_processing/05_nullable_auxiliary_values/README.md) |
| S05 | 15RCDVZ001 has 15,319 null prof_min references. Match profile rows by sampleNo; compare every available reference at 1e-4. Require usable evidence and retain channel, row and file checks. Null positions are not claimed as numerically compared. | [05](../special_processing/05_nullable_auxiliary_values/README.md) |
| S06 | Image bounds differ in decimal text but represent the same float32 value, such as 297.9254 and 297.92542. Try the 1e-5 decimal check first, then require equal finite float32 bits for both bounds. Historical evidence covers 37 holes and 1,197 tray records. | [06](../special_processing/06_float32_precision/README.md) |
| S07 | 24FNDD010 has one profile reference outside 1e-4: sample 179248 stores 1234100.25 versus 1234100.2. All 232,288 samples match at float32 precision. Preserve both values and verify all comparable rows rather than widening the tolerance. | [06](../special_processing/06_float32_precision/README.md) |
| S08 | Reviewed depth resets occur at sample 6030 in 16MYD0058 and 27800 in Acacia 1. Require registered IDs and exact tray/section boundaries; preserve depth and order. Reject other resets. Ordinary repeated depths already work normally. | [07](../special_processing/07_reviewed_depth_resets/README.md) |
| S09 | 24FNDD010 and ADD10 contain identical Tray/Section logs under different IDs. Recognize aliases only after comparison with the dataset-declared source; retain every source ID and file. Different content is rejected. | [03](../special_processing/03_duplicate_interval_logs/README.md) |
| S10 | The same holes contain duplicate image logs. Compare every hash, dataset ID, ordinal and declared depth. Select one display sequence by log ID only after complete equality; retain all original images. | [04](../special_processing/04_duplicate_image_logs/README.md) |
| S11 | Acacia 1 Formations contains a literal unmatched quote. For the registered log only, use QUOTE_NONE and preserve all 160,128 rows; retain three-column, hash and depth-axis checks. | [08](../special_processing/08_literal_text_csv/README.md) |
| S12 | Five registered text logs in ARMCDD001, ARMCRCD002A and BM5346 contain unescaped commas. Split at the first two commas, preserving the remaining text. Use the same parser during validation, alignment and Parquet writing; do not apply it to arbitrary multiline CSV. | [08](../special_processing/08_literal_text_csv/README.md) |
| S13 | Some wavelength axes in 24FNDD010 and ADD10 do not fit preset regions. Store UNCLASSIFIED while retaining coordinates, dimensions and matrices. Later media checks still verify ordering and sample binding. | [09](../special_processing/09_unclassified_spectral_axis/README.md) |
| S14 | Tamala step 31 reads both official responses as SpectralLogCollection. Select logCollection for scalar responses and SpectralLogCollection for spectra; retain evidence identity, hash, ID uniqueness and membership checks. | [11](../special_processing/11_multi_dataset_profile/README.md) |
| S15 | Tamala cuttings datasets both contain 680 samples. Use official dataset-specific prof_min logs and compare all candidate profile minima at 1e-4; require exactly one full match and prohibit reuse across datasets. Step 32 verifies alignment again. | [11](../special_processing/11_multi_dataset_profile/README.md) |
| S16 | A rerun produced logically equal Parquet with different bytes (2,365,100 versus 2,364,620 bytes). Historical reuse required matching on-disk schema and metadata, row groups, typed values and null masks. Value or metadata changes still failed. | Historical rerun issue; no raw-input handler |

Exact IDs, counts and registered rule versions are in [source instances](special_case_instances.md).
[Evidence extracts](special_case_evidence.json) retain historical record hashes.

## Historical validation scope

Earlier batch records cover 20261005, 20261010 and 20261011. The initial standalone
Tamala check covered steps 31–33 only: 7,390 samples, six spectral matrices and
55 row images, with no database import or upload. Three dataset axes remained
separate. Correct cuttings matches were 680/680 rows; swapped matches were 1/680.

The later external-handler tests have their own, narrower
[validation report](../special_processing/failure_workflow_validation.md).
Do not treat historical batch-copy changes as changes to the original `etl4/`.

## Decisions for previously deferred datasets

The project now retains core datasets only and excludes cuttings. The five
reviewed same-name borehole groups are to be split using
`<original-hole-name>-<source-name>`, with `unnamed` for an empty source name.
See [dataset selection and naming](dataset_selection.md) for the rationale,
affected holes and processing boundaries. External case 12 prepares core-only
inputs; case 13 prepares separate boreholes with their dataset coordinates,
using the owner-approved shared-coordinate-system assumption.
Both return new input packages to the normal preparation checks.

## Incomplete downloads still excluded

- 19AFRD2003 and 19AFRD2004 had incomplete downloads, including missing images.
  They were excluded; missing required files were not made optional.

Ordinary duplicate depths, supported nulls, metadata-only spectra, coordinate
declarations, unresolved domain references and is_public flags are not special
cases merely because they produce a notice. Infrastructure, API, upload retries
and disk cleanup are outside this input-handling catalogue.

New inputs must first fail normal processing, then satisfy the handler's source
conditions. Unknown cases remain pending. Changes to parsing or mapping require
an explicit rule-version change for the affected datasets.
