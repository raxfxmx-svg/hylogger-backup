# Sample Spectra and Single-Row Core Images

2026-09-09. Prepared, imported, validated and published the five ETL4 boreholes as release `fd02659c-dc3d-52ea-a8eb-c032b91e7624`. Previous release `20bbb134-501d-54bc-9428-5ee48b6801e4` remains readable with unchanged business records. D:/100demo was only a layout reference; three multi-dataset reference boreholes and AWS/API changes were outside this iteration. Later constraint/rerun findings remained open in [DATABASE_MEDIA_REVIEW.md](DATABASE_MEDIA_REVIEW.md).

| Result | Count/details |
|---|---|
| Real samples | 261,892; duplicate depths retain separate sample_no |
| Original trays / lossless PNG rows | 249 / 1,361 |
| Layout checks | 4, 5 and 6 rows; 20 templates, 34 visually inspected representatives, full geometry/source checks |
| Spectra | 8 original F32 matrices and 448 byte blocks |
| Independent reference spectra | 80 with explicit sampleNo; every reconstructed float32 channel matched |
| Database / foreign keys | 36 tables, including six new media tables; 74 foreign keys |
| Behaviour tests | 19, including cross-dataset cases, duplicate depths, missing images, invalid links and rollback |

`spectral_array`, `spectral_sample_map` and `spectral_block` provide matrix layouts, sample mappings and bounded reads. `image_region`, `image_sample_mapping` and `image_region_asset` connect visible rows, real samples and crops through dataset/log identities. VSWIR/TIR and interpretation VNIR/SWIR/TIR s/u identities remain distinct. Official service implementation and saved sampleNo responses support spectral ordering; equal dimensions alone do not.

Crops preserve native decoded pixels, gaps, labels and filler. Boundaries use separators near source Section positions or checked templates; fixed 9% inset was only an initial candidate. `sample_index_linear v1` is approximate, with left-to-right direction confirmed by the project owner. Exact pixel/depth errors and anchors remain NULL. Real depth always comes from scan_sample.md_m.

05KCD001 samples 129/130 both have depth 60.37269 m but occupy adjacent rows, resetting pointer ratio from 1 to 0. 07THD002 sample 15 is 62.50175 m; `Min1 sTSAS=Muscovite` and `Wt1 sTSAS=0.7219433188438416`, preserved without probability conversion.

| Storage | Bytes |
|---|---:|
| New row PNGs | 30,846,972 |
| New F32 copies | 0; reuse 819,799,776 bytes |
| Running database with history | 191,360,147 |
| Restored database | 149,376,147 |
| Compressed backup | 10,240,368 |
| 2,810 unique referenced file paths | 2,400,546,756 |

Selected local reads averaged 14.2 ms, p95 24.8 ms with caches; these are not cloud performance estimates. Dumps exclude object files.

Steps 20-22 lock/check sources and prepare spectral access; 23-27 group images, inspect layouts, bind samples and generate lossless crops; 28 imports media; 29 validates and optionally activates (`--no-activate` validates only). First-time official evidence uses `--fetch-reference`; visual review is recorded with `--record-reviewed`. This historical route starts from its original base release in an independent restored workspace.

Sealed outputs are under database/media_releases/<content_digest>; media_work holds stages and media_evidence holds references. Reused assets retain original revision/axis identities; readers use database mappings rather than old embedded Parquet axis IDs. The five-borehole adapter rejects real multi-dataset raw packages pending a dedicated preparation path. See [reader contract](MEDIA_READ_CONTRACT.md), [schema](schema_dictionary.md), [source mapping](source_to_table_mapping.md) and reports/29_media_verification.json.
