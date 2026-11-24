$ErrorActionPreference = "Stop"

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupDir = Join-Path $PSScriptRoot "..\backups"
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
$backupFile = Join-Path $backupDir "dawit-lottery-$timestamp.sql"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$process = Start-Process `
    -FilePath "docker" `
    -ArgumentList @("compose", "exec", "-T", "postgres", "pg_dump", "-U", "lottery", "-d", "dawit_lottery", "--format=custom", "--no-owner", "--no-acl") `
    -WorkingDirectory $projectRoot `
    -RedirectStandardOutput $backupFile `
    -Wait `
    -PassThru

if ($process.ExitCode -ne 0) {
    throw "Database backup failed with exit code $($process.ExitCode)"
}

Write-Output "Database backup created: $backupFile"
