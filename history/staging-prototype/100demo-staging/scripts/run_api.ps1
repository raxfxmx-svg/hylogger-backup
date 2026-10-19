$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Project virtual environment is missing: $python"
}

Push-Location $projectRoot
try {
    & $python -m uvicorn api.app:app `
        --host $(if ($env:HYLOGGER_API_HOST) { $env:HYLOGGER_API_HOST } else { "127.0.0.1" }) `
        --port $(if ($env:HYLOGGER_API_PORT) { $env:HYLOGGER_API_PORT } else { "8100" })
} finally {
    Pop-Location
}
