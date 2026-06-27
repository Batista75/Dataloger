param(
    [switch]$SkipInstall,
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"

$AppDir = Split-Path -Parent $PSScriptRoot
Set-Location $AppDir

$VenvPython = Join-Path $AppDir ".venv\Scripts\python.exe"
$VenvPip = Join-Path $AppDir ".venv\Scripts\pip.exe"

if (-not (Test-Path $VenvPython)) {
    Write-Host "[dev] Creation de l environnement virtuel"
    py -3 -m venv .venv
}

if (-not $SkipInstall) {
    Write-Host "[dev] Installation des dependances"
    & $VenvPip install --upgrade pip
    & $VenvPip install -r requirements.txt
}

Write-Host "[dev] Initialisation DB"
& $VenvPython -m src.db.init_db

Write-Host "[dev] Lancement API locale sur http://$BindHost`:$Port"
& $VenvPython -m uvicorn src.api.main:app --host $BindHost --port $Port --reload
