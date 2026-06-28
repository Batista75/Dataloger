param(
    [string]$RemoteHost = "192.168.1.87",
    [string]$RemoteUser = "mb",
    [int]$SshPort = 22,
    [string]$RemoteDir = "/home/mb/datalogger",
    [switch]$PushEnv,
    [switch]$SkipRestart
)

$ErrorActionPreference = "Stop"

$AppDir = Split-Path -Parent $PSScriptRoot
Set-Location $AppDir

if (-not (Get-Command ssh -ErrorAction SilentlyContinue)) {
    throw "ssh est introuvable. Installe OpenSSH client sur cette machine."
}
if (-not (Get-Command scp -ErrorAction SilentlyContinue)) {
    throw "scp est introuvable. Installe OpenSSH client sur cette machine."
}

$TmpDir = Join-Path $env:TEMP "datalogger-deploy"
if (Test-Path $TmpDir) {
    Remove-Item -Recurse -Force $TmpDir
}
New-Item -ItemType Directory -Path $TmpDir | Out-Null

$PackageRoot = Join-Path $TmpDir "package"
New-Item -ItemType Directory -Path $PackageRoot | Out-Null

$Items = @("src", "static", "tools", "scripts", "systemd", "docs", "requirements.txt", ".env.example")
foreach ($Item in $Items) {
    if (Test-Path $Item) {
        Copy-Item -Recurse -Force $Item -Destination (Join-Path $PackageRoot $Item)
    }
}

if ($PushEnv -and (Test-Path ".env")) {
    Copy-Item -Force ".env" -Destination (Join-Path $PackageRoot ".env")
}

$ArchivePath = Join-Path $TmpDir "datalogger_deploy.zip"
if (Test-Path $ArchivePath) {
    Remove-Item -Force $ArchivePath
}

# Build zip with POSIX paths so Linux extract overwrites files correctly.
$PackageRootUnix = ($PackageRoot -replace '\\', '/')
$ArchivePathUnix = ($ArchivePath -replace '\\', '/')
python -c @"
import zipfile
from pathlib import Path

root = Path(r'$PackageRoot')
archive = Path(r'$ArchivePath')
with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
    for path in root.rglob('*'):
        if path.is_file():
            zf.write(path, path.relative_to(root).as_posix())
print(f'ZIP_READY={archive}')
"@

$Remote = "$RemoteUser@$RemoteHost"
Write-Host "[deploy] Upload du package vers $Remote"
& scp -P $SshPort $ArchivePath "${Remote}:/tmp/datalogger_deploy.zip"

$remoteLines = @(
        "set -eu",
        "mkdir -p '$RemoteDir'",
        "python3 -c ""import zipfile; z=zipfile.ZipFile('/tmp/datalogger_deploy.zip'); z.extractall('$RemoteDir'); z.close()""",
        "find '$RemoteDir' -name '__MACOSX' -type d -prune -exec rm -rf {} + 2>/dev/null || true",
        "cd '$RemoteDir'",
        "chmod +x scripts/*.sh || true",
        "if [ -d .venv ]; then ./scripts/update.sh; else ./scripts/setup.sh; fi"
)

if (-not $SkipRestart) {
        $remoteLines += "sudo systemctl restart datalogger.service"
        $remoteLines += "if grep -Eqi '^TUYA_ENABLED=(1|true|yes|on)`$' .env; then sudo systemctl restart datalogger-tuya.service; fi"
}

$remoteLines += "printf 'API: '"
$remoteLines += "sudo systemctl is-active datalogger.service"
$remoteLines += "if systemctl list-unit-files 2>/dev/null | grep -q '^datalogger-tuya.service'; then printf ' TUYA: '; sudo systemctl is-active datalogger-tuya.service || true; fi"
$remoteLines += "echo"

$RemoteScript = ($remoteLines -join "`n")

Write-Host "[deploy] Installation/update sur le Raspberry"
($RemoteScript -replace "`r", "") | & ssh -p $SshPort $Remote "bash -s"

Write-Host "[deploy] Termine"
