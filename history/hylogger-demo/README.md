# HyLogger 05GJD001 Core Explorer

This local Dash application displays only the supplied `05GJD001` HyLogger
package. It connects all 33 source photographs to their recorded absolute depth
ranges and shows the actual `Grp1 sTSAS` NIR group output in 0.1 m display bins.

No other holes or locations are included. Latitude, longitude, and confidence
were not supplied, so those fields remain blank and are never inferred.

## Start on Windows

Open PowerShell in this project folder and run:

```powershell
.\run.ps1
```

If PowerShell blocks local scripts, use a process-only bypass:

```powershell
powershell -ExecutionPolicy Bypass -File .\run.ps1
```

Open `http://127.0.0.1:8050`. The script uses port 8051 only when 8050 is
already listening. Press `Ctrl+C` in PowerShell to stop the app.

## Use the page

1. Confirm the hole record: only `05GJD001` is present and coordinates are blank.
2. Choose one of the 33 trays. Tray `0001` is the default and covers
   `150.000–154.679159 m`.
3. The page requests only that tray's resized photograph.
4. Read the matching absolute-depth profile and hover a 0.1 m strip for its
   dominant real NIR group and sample counts.
5. Treat `dominant_share_pct` as a within-bin count share, not confidence.
   `NO RESULT`, `INVALID`, and `NOTAROK` remain explicit.

## Tests

```powershell
.\.venv\Scripts\python.exe -m compileall app.py src scripts tests
.\.venv\Scripts\python.exe -m pytest
```

## Re-extract the local source package

The project environment contains `pytsg` and Pillow. This command regenerates
the auditable sample export, tray table, 0.1 m bins, metadata, and all 33
web-sized images:

```powershell
.\.venv\Scripts\python.exe .\scripts\extract_scan_summary.py ..\8a294cfc-68df-4f03-995b-c5fd0d47ab0
```

The large spectra remain in the original package. The browser receives only
the current tray image and compact extracted records.

## Future data

Authoritative latitude and longitude can later be entered in `data/holes.csv`.
Until both values exist, the app intentionally renders no map. Additional holes
should be imported as separate real packages rather than created as demo rows.
