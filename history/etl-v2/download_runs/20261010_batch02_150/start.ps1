$ErrorActionPreference = 'Stop'
$runDir = $PSScriptRoot
foreach ($fileName in @('launcher.json', 'process.json')) {
    $priorPath = Join-Path $runDir $fileName
    if (Test-Path -LiteralPath $priorPath) {
        $prior = Get-Content -LiteralPath $priorPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($fileName -eq 'launcher.json') { $priorId = $prior.runner_pid } else { $priorId = $prior.download_pid }
        if ($priorId) {
            $priorProcess = Get-Process -Id $priorId -ErrorAction SilentlyContinue
            if ($priorProcess -and ($priorProcess.StartTime.ToUniversalTime().ToString('o') -eq $prior.process_start_utc)) {
                throw "This batch is already running (PID $priorId)."
            }
        }
    }
}
$stopPath = Join-Path $runDir 'stop.requested'
if (Test-Path -LiteralPath $stopPath) { Remove-Item -LiteralPath $stopPath }
$shellPath = Join-Path $PSHOME 'powershell.exe'
if (-not (Test-Path -LiteralPath $shellPath)) { $shellPath = Join-Path $PSHOME 'pwsh.exe' }
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss_fff'
$runner = Start-Process -FilePath $shellPath -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ('"{0}"' -f (Join-Path $runDir 'runner.ps1'))) -WorkingDirectory $runDir -WindowStyle Hidden -RedirectStandardOutput (Join-Path $runDir ($stamp + '_runner.log')) -RedirectStandardError (Join-Path $runDir ($stamp + '_runner.err.log')) -PassThru
$info = [ordered]@{ runner_pid = $runner.Id; process_start_utc = $runner.StartTime.ToUniversalTime().ToString('o'); run_directory = $runDir }
$json = $info | ConvertTo-Json
[System.IO.File]::WriteAllText((Join-Path $runDir 'launcher.json'), $json, (New-Object System.Text.UTF8Encoding($false)))
Write-Output $json
