param(
    [Parameter(Mandatory = $true)]
    [string]$BackupFile
)

$ErrorActionPreference = "Stop"
$resolvedBackup = (Resolve-Path $BackupFile).Path

Write-Warning "This will replace the current database contents."
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$process = Start-Process `
    -FilePath "docker" `
    -ArgumentList @("compose", "exec", "-i", "postgres", "pg_restore", "-U", "lottery", "-d", "dawit_lottery", "--clean", "--if-exists", "--no-owner", "--no-acl") `
    -WorkingDirectory $projectRoot `
    -RedirectStandardInput $resolvedBackup `
    -Wait `
    -PassThru

if ($process.ExitCode -ne 0) {
    throw "Database restore failed with exit code $($process.ExitCode)"
}
