# HyLogger 100-Hole Workspace

This independent staging workspace combines NVCL downloads, ETL, PostgreSQL/PostGIS and a read-only API. Historical location: D:/100demo; database: hylogger_100demo; API: http://127.0.0.1:8100.

The [midterm results](../../../evidence/midterm-demo/README.md) record 96 verified holes, 5,863,516 samples and 41,668 core-section image strips. The configuration here preserves the earlier staging snapshot; the results folder contains the later hole-status list.

The batch runner reconciles its manifest against api.current_holes, skips already verified holes and records status in config/wa_demo_100.csv, replacement history in data/batch_runs/replacement_history.jsonl, and per-run logs under data/batch_runs/<run_id>. Missing optional high-resolution images, profilometer data or spectra remain unavailable/warning; another hole's data is never substituted.

## Commands

```powershell
cd D:\100demo

# Read-only precheck using the current database state
.\.venv\Scripts\python.exe .\scripts\batch_100.py --mode remaining --workers 2 --wave-size 10 --target-count 100 --max-consecutive-failures 3 --dry-run

# Resume in ten-hole waves with two concurrent holes; ETL, validation and import remain sequential per hole
.\.venv\Scripts\python.exe .\scripts\batch_100.py --mode remaining --workers 2 --wave-size 10 --target-count 100 --max-consecutive-failures 3

# Start the read-only API
.\scripts\run_api.ps1
```
