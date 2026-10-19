[CmdletBinding()]
param(
    [string]$Database = "hylogger_100demo",
    [string]$HostName = "localhost",
    [int]$Port = 5432,
    [string]$User = "postgres",
    [string]$Label = "snapshot",
    [string]$PgDumpPath = "C:\Program Files\PostgreSQL\17\bin\pg_dump.exe"
)

$ErrorActionPreference = "Stop"
if (-not $env:PGPASSWORD) {
    throw "Set PGPASSWORD in the current terminal before creating a backup."
}
if (-not (Test-Path -LiteralPath $PgDumpPath -PathType Leaf)) {
    throw "pg_dump not found: $PgDumpPath"
}

$projectRoot = Split-Path -Parent $PSScriptRoot
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$safeLabel = $Label -replace '[^A-Za-z0-9_-]', '_'
$snapshotRoot = Join-Path $projectRoot "backups\100demo_${safeLabel}_$stamp"
$databaseRoot = Join-Path $snapshotRoot "database"
$filesRoot = Join-Path $snapshotRoot "files"
New-Item -ItemType Directory -Path $databaseRoot -Force | Out-Null
New-Item -ItemType Directory -Path $filesRoot -Force | Out-Null

$dumpPath = Join-Path $databaseRoot "${Database}.dump"
& $PgDumpPath -w -h $HostName -p $Port -U $User -d $Database -F c -f $dumpPath
if ($LASTEXITCODE -ne 0) {
    throw "pg_dump failed with exit code $LASTEXITCODE"
}

function Copy-Tree([string]$Source, [string]$Destination) {
    if (-not (Test-Path -LiteralPath $Source -PathType Container)) {
        return
    }
    & robocopy $Source $Destination /E /R:2 /W:5 /COPY:DAT /DCOPY:DAT /NFL /NDL /NP
    if ($LASTEXITCODE -gt 7) {
        throw "robocopy failed for $Source with exit code $LASTEXITCODE"
    }
}

Copy-Tree (Join-Path $projectRoot "config") (Join-Path $filesRoot "config")
Copy-Tree (Join-Path $projectRoot "data\raw") (Join-Path $filesRoot "data\raw")
Copy-Tree (Join-Path $projectRoot "data\processed") (Join-Path $filesRoot "data\processed")
Copy-Tree (Join-Path $projectRoot "data\batch_runs") (Join-Path $filesRoot "data\batch_runs")
Copy-Item -LiteralPath (Join-Path $projectRoot "README.md") -Destination $filesRoot

$fileStats = Get-ChildItem -LiteralPath $filesRoot -File -Recurse | Measure-Object -Property Length -Sum
$manifest = [ordered]@{
    created_at = (Get-Date).ToString("o")
    label = $Label
    database = $Database
    database_dump = $dumpPath
    copied_roots = @("config", "data/raw", "data/processed", "data/batch_runs")
    file_count = $fileStats.Count
    file_bytes = [long]$fileStats.Sum
}
$manifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $snapshotRoot "backup_manifest.json") -Encoding utf8
Write-Host "Combined backup written to $snapshotRoot"
