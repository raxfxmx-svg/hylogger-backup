# Extracted 05GJD001 data

Every active data file in this folder is derived from the supplied
`8a294cfc-68df-4f03-995b-c5fd0d47ab0` package, except the deliberately empty
coordinate fields in `holes.csv`.

- `holes.csv` contains the real hole ID. Latitude and longitude are blank
  because the package does not supply authoritative coordinates.
- `05GJD001_trays.csv` maps all 33 tray photographs to their recorded depth
  ranges and web-image paths.
- `05GJD001_sample_groups.csv` is an auditable 25,938-row export of sample
  depths and the real `Grp1 sTSAS` value.
- `05GJD001_depth_bins.csv` groups the samples into 0.1 m display bins. The
  displayed label is the most frequent real group inside each bin, and
  `dominant_share_pct` is only a within-bin count share—not confidence.
- `05GJD001_scan_summary.csv` contains whole-hole group counts.
- `05GJD001_scan_metadata.json` records package, depth, wavelength, channel,
  coordinate, confidence, and provenance status.

The application does not infer coordinates or confidence. `NO RESULT`,
`INVALID`, and `NOTAROK` remain explicit outputs.
