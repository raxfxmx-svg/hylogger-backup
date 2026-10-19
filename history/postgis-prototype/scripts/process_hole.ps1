[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[A-Za-z0-9_-]+$')]
    [string]$HoleId
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$rawDir = Join-Path $projectRoot "data\raw\$HoleId"
$processedRoot = Join-Path $projectRoot "data\processed"

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Project virtual environment is missing: $python"
}
if (-not (Test-Path -LiteralPath $rawDir -PathType Container)) {
    throw "Downloader output is missing: $rawDir"
}
if (-not $env:HYLOGGER_DB_USER) {
    throw "Set HYLOGGER_DB_USER in the current terminal."
}
if (-not ($env:HYLOGGER_DB_PASSWORD -or $env:PGPASSWORD)) {
    throw "Set HYLOGGER_DB_PASSWORD or PGPASSWORD in the current terminal."
}

Push-Location $projectRoot
try {
    & $python .\pipeline\etl.py $HoleId `
        --raw-root .\data\raw `
        --processed-root .\data\processed
    if ($LASTEXITCODE -ne 0) { throw "ETL3 transform failed" }

    $current = Get-Content -LiteralPath (Join-Path $processedRoot "current.json") -Raw | ConvertFrom-Json
    $releaseId = [string]$current.release_id

    & $python .\pipeline\verify.py --project-root $projectRoot --release-id $releaseId
    if ($LASTEXITCODE -ne 0) { throw "ETL3 release verification failed" }

    & (Join-Path $PSScriptRoot "import_release.ps1") -ReleaseId $releaseId -HoleId $HoleId
    if ($LASTEXITCODE -ne 0) { throw "PostgreSQL import workflow failed" }

    Write-Host "Hole $HoleId is active in PostgreSQL as release $releaseId"
} finally {
    Pop-Location
}
