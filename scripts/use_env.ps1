param(
    [ValidateSet("dev", "prod")]
    [string]$Profile = "dev"
)

$ErrorActionPreference = "Stop"
$AppDir = Split-Path -Parent $PSScriptRoot
Set-Location $AppDir

$Template = if ($Profile -eq "dev") { ".env.dev.example" } else { ".env.prod.example" }
if (-not (Test-Path $Template)) {
    throw "Template introuvable: $Template"
}

if (Test-Path ".env") {
    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    Copy-Item ".env" ".env.backup.$timestamp" -Force
    Write-Host "[env] Backup cree: .env.backup.$timestamp"
}

Copy-Item $Template ".env" -Force
Write-Host "[env] Profil applique: $Profile"
Write-Host "[env] Fichier actif: .env"
