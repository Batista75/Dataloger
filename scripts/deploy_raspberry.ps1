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
Compress-Archive -Path (Join-Path $PackageRoot "*") -DestinationPath $ArchivePath

$Remote = "$RemoteUser@$RemoteHost"
Write-Host "[deploy] Upload du package vers $Remote"
& scp -P $SshPort $ArchivePath "$Remote:/tmp/datalogger_deploy.zip"

$RemoteScript = @"
set -euo pipefail
mkdir -p '$RemoteDir'
python3 - <<'PY'
import zipfile
zipfile.ZipFile('/tmp/datalogger_deploy.zip').extractall('$RemoteDir')
PY
cd '$RemoteDir'
chmod +x scripts/*.sh || true
if [ -d .venv ]; then
  ./scripts/update.sh
else
  ./scripts/setup.sh
fi
"@

if (-not $SkipRestart) {
    $RemoteScript += @"
sudo systemctl restart datalogger.service
if grep -Eqi '^TUYA_ENABLED=(1|true|yes|on)$' .env; then
  sudo systemctl restart datalogger-tuya.service
fi
"@
}

$RemoteScript += @"
printf 'API: '
sudo systemctl is-active datalogger.service
if systemctl list-unit-files | grep -q '^datalogger-tuya.service'; then
  printf 'TUYA: '
sudo systemctl is-active datalogger-tuya.service || true
fi
"@

Write-Host "[deploy] Installation/update sur le Raspberry"
$RemoteScript | & ssh -p $SshPort $Remote "bash -s"

Write-Host "[deploy] Termine"
