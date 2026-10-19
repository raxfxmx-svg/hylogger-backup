$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $ProjectRoot

$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $VenvPython)) {
    Write-Host "Creating local virtual environment..."
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 -m venv (Join-Path $ProjectRoot ".venv")
    }
    elseif (Get-Command python -ErrorAction SilentlyContinue) {
        & python -m venv (Join-Path $ProjectRoot ".venv")
    }
    else {
        throw "Python 3.10 or newer was not found. Install Python, then run this script again."
    }
}

Write-Host "Installing or confirming project dependencies..."
& $VenvPython -m pip install --disable-pip-version-check -r (Join-Path $ProjectRoot "requirements.txt")

if (-not $env:HYLOGGER_PORT) {
    $SelectedPort = 8050
    if (Get-NetTCPConnection -LocalPort 8050 -State Listen -ErrorAction SilentlyContinue) {
        $SelectedPort = 8051
    }
    $env:HYLOGGER_PORT = [string]$SelectedPort
}

$env:PYTHONUTF8 = "1"
Write-Host "Starting HyLogger Drill-Core Explorer"
Write-Host "Open http://127.0.0.1:$($env:HYLOGGER_PORT) in your browser. Press Ctrl+C to stop."
& $VenvPython (Join-Path $ProjectRoot "app.py")

