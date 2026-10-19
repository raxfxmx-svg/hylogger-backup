[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ReleaseId,
    [string]$HoleId = ""
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$release = Join-Path $projectRoot "data\processed\releases\$ReleaseId"

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Project virtual environment is missing: $python"
}
if (-not (Test-Path -LiteralPath $release -PathType Container)) {
    throw "Release directory is missing: $release"
}
if (-not $env:HYLOGGER_DB_USER) {
    throw "Set HYLOGGER_DB_USER in the current terminal."
}
if (-not ($env:HYLOGGER_DB_PASSWORD -or $env:PGPASSWORD)) {
    throw "Set HYLOGGER_DB_PASSWORD or PGPASSWORD in the current terminal."
}

Push-Location $projectRoot
try {
    & $python -m etl.load_release $release --check-only
    if ($LASTEXITCODE -ne 0) { throw "Release preflight failed" }

    $roleArgs = @()
    if ($env:HYLOGGER_DB_SET_ROLE) {
        $roleArgs = @("--set-role", $env:HYLOGGER_DB_SET_ROLE)
    }
    & $python -m etl.load_release $release @roleArgs
    if ($LASTEXITCODE -ne 0) { throw "PostgreSQL load failed" }

    if (-not $HoleId) {
        $manifest = Get-Content -LiteralPath (Join-Path $release "release_manifest.json") -Raw | ConvertFrom-Json
        $HoleId = [string]$manifest.holes[0]
    }
    & $python -m etl.verify_loaded $HoleId @roleArgs
    if ($LASTEXITCODE -ne 0) { throw "Post-load verification failed" }
} finally {
    Pop-Location
}
