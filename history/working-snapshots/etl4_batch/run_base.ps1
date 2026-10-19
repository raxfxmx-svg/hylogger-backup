param([int]$FromStep = 1, [int]$ToStep = 10)
$ErrorActionPreference = 'Stop'
$project = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$python = Join-Path $project 'etl4/database/.venv/Scripts/python.exe'
$work = Join-Path $project 'etl4/batch_check'
$list = Join-Path $work 'input_selection/single_holes.txt'
$records = @()
foreach ($step in $FromStep..$ToStep) {
    if ((Get-PSDrive C).Free -lt 10GB) { throw 'Drive C has less than 10 GiB free; stop generating new outputs.' }
    $folder = if ($step -le 6) { 'processing' } else { 'database' }
    $script = Get-ChildItem (Join-Path $project "etl4/$folder/${step}_*.py")
    $arguments = @('-B', '-X', 'utf8', $script.FullName, '--work-dir', $work, '--dbname', 'etl4_batch_check')
    if ($step -le 6) { $arguments += @('--holes-file', $list) }
    if ($step -eq 7) { $arguments += '--inputs-only' }
    $log = Join-Path $PSScriptRoot "full_step_$step.log"
    $started = Get-Date
    Write-Output "Running step $step; log: $log"
    & $python @arguments *> $log
    $code = $LASTEXITCODE
    $records += [pscustomobject]@{ step = $step; seconds = ((Get-Date) - $started).TotalSeconds; exit_code = $code }
    $records | ConvertTo-Json -AsArray | Set-Content (Join-Path $PSScriptRoot "base_progress_from_$FromStep.json") -Encoding utf8
    Write-Output "Step $step finished: exit $code"
    if ($code -ne 0) { throw "Step $step failed; inspect $log" }
}
