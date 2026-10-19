[CmdletBinding()]
param(
    [string]$Database = "hylogger_100demo",
    [string]$HostName = "localhost",
    [int]$Port = 5432,
    [string]$User = "postgres",
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
$backupRoot = Join-Path $projectRoot "backups"
New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$safeDatabase = $Database -replace '[^A-Za-z0-9_-]', '_'
$output = Join-Path $backupRoot "${safeDatabase}_$stamp.dump"

& $PgDumpPath -w -h $HostName -p $Port -U $User -d $Database -F c -f $output
if ($LASTEXITCODE -ne 0) {
    throw "pg_dump failed with exit code $LASTEXITCODE"
}
Write-Host "Database backup written to $output"
