$ErrorActionPreference = 'Stop'
$stopPath = Join-Path $PSScriptRoot 'stop.requested'
[System.IO.File]::WriteAllText($stopPath, [DateTime]::UtcNow.ToString('o'))
Write-Output 'Pause requested. In-flight requests may take time to return. See progress.json and process.json; do not force-kill Python.'
