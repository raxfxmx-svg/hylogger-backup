# Per-Sample Spectra and Image Links

This 2026-09-08 plan preserved every source spectral record and wavelength channel and proposed evidence-backed sample/image links. The five-hole implementation followed on 2026-09-09; see [MEDIA_DELIVERY.md](MEDIA_DELIVERY.md) and the [single-row image plan](SINGLE_ROW_IMAGE_PLAN.md).

I separated complete spectral values from their visualization. The database stores identities, full wavelength axes, matrix descriptions, byte ranges, sample mappings and provenance; F32 arrays and images remain file assets. Unknown units and layouts remain unknown, and equal record/sample counts alone do not prove binding.

The initial files contained eight F32 arrays totaling 819,799,776 bytes. VSWIR had 531 channels over 380–2500 nm; TIR had 341 over 6000–14500 nm. These are observed batch properties, not universal constraints. VSWIR sample counts were 22,356, 116,424, 54,432, 46,030 and 22,650 for the five original holes. Only the first three had downloaded TIR payloads. All 249 tray thumbnails and 28,103 repeated-depth samples were retained.

For a verified sample-contiguous float32 layout, `start_byte = data_offset_bytes + i * wavelength_count * item_size_bytes` and `byte_length = wavelength_count * item_size_bytes`. One VSWIR record uses 2,124 bytes; one TIR record uses 1,364. Windows of 64, 256 and 1,024 records were proposed for measurement. Rearranged service copies would require full value/mask comparison with originals.

The proposed spectral_array, spectral_sample_map and spectral_block tables describe decoding, real-sample relationships and bounded reads. Composite foreign keys keep logs, axes, matrices and assets within one revision. Counts, channel order, byte limits and first/last/window-boundary reads require verification against independent source evidence. Existing Parquet row_group fields are not reused as F32 byte offsets.

Images use independent region, sample-mapping and asset records. Actual depth/results come from samples; the approximate row indicator uses `p=(s-a)/(b-a)`, 0.5 for one sample, and `x=p*(W-1)`. Exact pixel-depth calibration, high-resolution photos and spatial spectral cubes are separate capabilities and cannot be inferred from thumbnails or record matrices.

Steps 20–29 were planned to audit sources, verify bindings, prepare spectral access, group and crop images, bind rows, import new revisions and validate bounded reads. Original files, unknown states and earlier releases remain preserved. API/frontend integration and cloud network performance were separate later work.
