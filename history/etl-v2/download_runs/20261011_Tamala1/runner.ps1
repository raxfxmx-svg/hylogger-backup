$ErrorActionPreference = 'Stop'
$runDir = $PSScriptRoot
$pythonPath = 'D:\100demo\.venv\Scripts\python.exe'
$downloadPath = 'C:\path\to\project\etl2\download.py'
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss_fff'
$stdoutPath = Join-Path $runDir ($stamp + '_download.log')
$stderrPath = Join-Path $runDir ($stamp + '_download.err.log')
$statePath = Join-Path $runDir 'process.json'
function Write-State($value) {
    $json = $value | ConvertTo-Json -Depth 6
    [System.IO.File]::WriteAllText(($statePath + '.tmp'), $json, (New-Object System.Text.UTF8Encoding($false)))
    Move-Item -LiteralPath ($statePath + '.tmp') -Destination $statePath -Force
}
try {
    $downloadArguments = @(
        '-B', '-u', '-X', 'utf8', ('"{0}"' -f $downloadPath),
        '--holes-file', ('"{0}"' -f (Join-Path $runDir 'holes.txt')),
        '--provider', 'wa', '--out', '"D:\100demo\data"',
        '--cache', '"D:\100demo\data\cache"', '--workers', '1', '--min-free-gib', '30',
        '--progress-file', ('"{0}"' -f (Join-Path $runDir 'progress.json')),
        '--stop-file', ('"{0}"' -f (Join-Path $runDir 'stop.requested'))
    )
    $downloadProcess = Start-Process -FilePath $pythonPath -ArgumentList $downloadArguments -WorkingDirectory (Split-Path -Parent $downloadPath) -WindowStyle Hidden -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath -PassThru
    $state = [ordered]@{
        status = 'running'; requested = 1; workers = 1; reserve_gib = 30
        runner_pid = $PID; download_pid = $downloadProcess.Id
        process_start_utc = $downloadProcess.StartTime.ToUniversalTime().ToString('o')
        stdout = $stdoutPath; stderr = $stderrPath
        raw_directory = 'D:\100demo\data\raw'; cache_directory = 'D:\100demo\data\cache'
    }
    Write-State $state
    $downloadProcess.WaitForExit()
    $downloadProcess.Refresh()
    $state['exit_code'] = $downloadProcess.ExitCode
    $state['finished_utc'] = [DateTime]::UtcNow.ToString('o')
    $state['status'] = switch ($downloadProcess.ExitCode) { 0 { 'finished' }; 2 { 'paused' }; default { 'failed_or_partial' } }
    Write-State $state
} catch {
    Write-State ([ordered]@{ status = 'launcher_error'; message = $_.Exception.Message; stdout = $stdoutPath; stderr = $stderrPath })
    throw
}
