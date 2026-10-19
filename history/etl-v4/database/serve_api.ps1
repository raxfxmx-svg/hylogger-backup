param([switch]$Stop)
$ErrorActionPreference = 'Stop'
$databaseRoot = $PSScriptRoot
$statePath = Join-Path $databaseRoot 'runtime/api_process.json'
if (Test-Path -LiteralPath $statePath) {
    $state = Get-Content -LiteralPath $statePath -Raw -Encoding utf8 | ConvertFrom-Json
    $apiProcessId = [int]$state.pid
    $existing = Get-CimInstance Win32_Process -Filter "ProcessId=$apiProcessId"
    if ($existing) {
        if ($existing.CommandLine -notlike '*uvicorn api.app:app*' -or $existing.ExecutablePath -ne (Join-Path $databaseRoot '.venv/Scripts/python.exe').Replace('/','\')) {
            throw 'Saved process ID belongs to a different process; refusing to control it.'
        }
        if ($Stop) {
            # Windows venv launchers can own a separate Python child; stop this
            # verified launcher tree so the actual server is not orphaned.
            & taskkill.exe /PID $apiProcessId /T /F
            if ($LASTEXITCODE -ne 0) { throw 'Failed to stop the verified ETL4 API process tree.' }
            Write-Output 'ETL4 API stopped'; return
        }
        Write-Output 'ETL4 API is already running at http://127.0.0.1:58000/docs'; return
    }
}
if ($Stop) { Write-Output 'ETL4 API is not running'; return }
if (Get-NetTCPConnection -LocalPort 58000 -State Listen -ErrorAction SilentlyContinue) { throw 'Port 58000 is already in use.' }
$pythonExe = Join-Path $databaseRoot '.venv/Scripts/python.exe'
$apiProcess = Start-Process -FilePath $pythonExe -ArgumentList @('-X','utf8','-m','uvicorn','api.app:app','--host','127.0.0.1','--port','58000','--no-access-log') -WorkingDirectory $databaseRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $databaseRoot 'runtime/api_stdout.log') -RedirectStandardError (Join-Path $databaseRoot 'runtime/api_stderr.log')
[System.IO.File]::WriteAllText($statePath, (@{pid=$apiProcess.Id; host='127.0.0.1'; port=58000; module='api.app:app'} | ConvertTo-Json), [System.Text.UTF8Encoding]::new($false))
Write-Output 'ETL4 API starting at http://127.0.0.1:58000/docs'
