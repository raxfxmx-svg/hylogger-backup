[CmdletBinding()]
param(
    [string]$Database = "hylogger_100demo",
    [string]$HostName = "localhost",
    [int]$Port = 5432,
    [string]$AdminUser = "postgres",
    [string]$PsqlPath = "C:\Program Files\PostgreSQL\17\bin\psql.exe"
)

$ErrorActionPreference = "Stop"
if ($Database -notmatch '^[A-Za-z_][A-Za-z0-9_]*$') {
    throw "Database name contains unsupported characters: $Database"
}
if (-not (Test-Path -LiteralPath $PsqlPath -PathType Leaf)) {
    throw "psql not found: $PsqlPath"
}
if (-not $env:PGPASSWORD) {
    throw "Set PGPASSWORD in the current terminal before database setup."
}

$connection = @("-X", "-w", "-h", $HostName, "-p", "$Port", "-U", $AdminUser, "-d", "postgres", "-v", "ON_ERROR_STOP=1")
$exists = [string](& $PsqlPath @connection -Atc "SELECT 1 FROM pg_database WHERE datname = '$Database';")
if ($LASTEXITCODE -ne 0) { throw "Could not inspect database list" }
$existsText = if ($null -eq $exists) { "" } else { $exists.Trim() }
if (-not $existsText) {
    & $PsqlPath @connection -c "CREATE DATABASE $Database;"
    if ($LASTEXITCODE -ne 0) { throw "Database creation failed" }
    Write-Host "Database $Database created."
} else {
    Write-Host "Database $Database already exists."
}

& (Join-Path $PSScriptRoot "..\db\apply_migrations.ps1") `
    -Database $Database -HostName $HostName -Port $Port -AdminUser $AdminUser -PsqlPath $PsqlPath
if ($LASTEXITCODE -ne 0) { throw "Database migrations failed" }
