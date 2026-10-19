[CmdletBinding()]
param(
    [string]$Database = "hylogger",
    [string]$HostName = "localhost",
    [int]$Port = 5432,
    [string]$AdminUser = "postgres",
    [string]$PsqlPath = "C:\Program Files\PostgreSQL\17\bin\psql.exe"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $PsqlPath -PathType Leaf)) {
    throw "psql not found: $PsqlPath"
}
if (-not $env:PGPASSWORD) {
    throw "Set PGPASSWORD in the current terminal before running migrations."
}

$dbDir = Split-Path -Parent $PSCommandPath
$bootstrap = Join-Path $dbDir "bootstrap_roles.sql"
$migrationDir = Join-Path $dbDir "migrations"
$connection = @("-X", "-w", "-h", $HostName, "-p", "$Port", "-U", $AdminUser, "-d", $Database, "-v", "ON_ERROR_STOP=1")

& $PsqlPath @connection -f $bootstrap
if ($LASTEXITCODE -ne 0) {
    throw "Role bootstrap failed with exit code $LASTEXITCODE"
}

$migrationFiles = Get-ChildItem -LiteralPath $migrationDir -Filter "*.sql" -File | Sort-Object Name
foreach ($migration in $migrationFiles) {
    if ($migration.BaseName -notmatch '^(\d+)_') {
        throw "Migration filename must start with a numeric version: $($migration.Name)"
    }
    $version = [int]$Matches[1]
    $sha256 = (Get-FileHash -LiteralPath $migration.FullName -Algorithm SHA256).Hash.ToLowerInvariant()

    $tableExists = [string](& $PsqlPath @connection -Atc "SELECT to_regclass('ops.schema_migrations') IS NOT NULL;")
    $tableExists = $tableExists.Trim()
    if ($LASTEXITCODE -ne 0) {
        throw "Could not inspect migration state"
    }

    if ($tableExists -eq "t") {
        $existing = [string](& $PsqlPath @connection -Atc "SELECT sha256 FROM ops.schema_migrations WHERE version = $version;")
        if ($null -eq $existing) {
            $existing = ""
        } else {
            $existing = $existing.Trim()
        }
        if ($LASTEXITCODE -ne 0) {
            throw "Could not inspect migration $version"
        }
        if ($existing) {
            if ($existing -ne $sha256) {
                throw "Migration $version was already applied with a different SHA-256. Add a new migration instead of editing an applied file."
            }
            Write-Host "Migration $version already applied; skipped."
            continue
        }
    }

    & $PsqlPath @connection -v "migration_sha=$sha256" -f $migration.FullName
    if ($LASTEXITCODE -ne 0) {
        throw "Migration $version failed with exit code $LASTEXITCODE"
    }
    Write-Host "Migration $version applied."
}

& $PsqlPath @connection -c "SELECT version, name, sha256, applied_at FROM ops.schema_migrations ORDER BY version;"
if ($LASTEXITCODE -ne 0) {
    throw "Final migration verification failed"
}
