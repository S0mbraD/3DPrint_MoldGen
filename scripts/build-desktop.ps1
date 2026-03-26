# MoldGen Desktop Build Script (Windows PowerShell)
# Usage: .\scripts\build-desktop.ps1 [-Release] [-SkipBackend] [-GenerateKeys]

param(
    [switch]$Release,
    [switch]$SkipBackend,
    [switch]$GenerateKeys
)

$ErrorActionPreference = "Stop"
$ROOT = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
if (-not $ROOT) { $ROOT = (Get-Location).Path }

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  MoldGen Desktop Build" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# ── Step 1: Check prerequisites ──────────────────────────────────────
Write-Host "[1/6] Checking prerequisites..." -ForegroundColor Yellow

$cmds = @("node", "npm", "cargo", "python")
foreach ($cmd in $cmds) {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
        Write-Host "  ERROR: '$cmd' not found in PATH" -ForegroundColor Red
        exit 1
    }
}
Write-Host "  All prerequisites found" -ForegroundColor Green

# ── Step 2: Generate signing keys (if requested) ─────────────────────
if ($GenerateKeys) {
    Write-Host "[2/6] Generating update signing keys..." -ForegroundColor Yellow
    $keyDir = "$env:USERPROFILE\.tauri"
    if (-not (Test-Path $keyDir)) {
        New-Item -ItemType Directory -Path $keyDir -Force | Out-Null
    }
    Set-Location "$ROOT\frontend"
    npx tauri signer generate -w "$keyDir\moldgen.key"
    Write-Host "  Keys saved to $keyDir\moldgen.key" -ForegroundColor Green
    Write-Host "  PUBLIC KEY (add to tauri.conf.json plugins.updater.pubkey):" -ForegroundColor Yellow
    Get-Content "$keyDir\moldgen.key.pub"
    Write-Host ""
} else {
    Write-Host "[2/6] Skipping key generation (use -GenerateKeys to create)" -ForegroundColor DarkGray
}

# ── Step 3: Build Python backend (PyInstaller) ──────────────────────
if (-not $SkipBackend) {
    Write-Host "[3/6] Building Python backend..." -ForegroundColor Yellow
    Set-Location $ROOT

    if (-not (Get-Command "pyinstaller" -ErrorAction SilentlyContinue)) {
        Write-Host "  Installing PyInstaller..." -ForegroundColor DarkGray
        pip install pyinstaller --quiet
    }

    pyinstaller --noconfirm --clean `
        --name moldgen-server `
        --onedir `
        --hidden-import moldgen `
        --hidden-import uvicorn `
        --hidden-import fastapi `
        --add-data "moldgen;moldgen" `
        --distpath "frontend/src-tauri/binaries" `
        moldgen/main.py

    Write-Host "  Backend bundled to frontend/src-tauri/binaries/" -ForegroundColor Green
} else {
    Write-Host "[3/6] Skipping backend build" -ForegroundColor DarkGray
}

# ── Step 4: Install frontend dependencies ────────────────────────────
Write-Host "[4/6] Installing frontend dependencies..." -ForegroundColor Yellow
Set-Location "$ROOT\frontend"
npm install --silent

# ── Step 5: Build Tauri app ──────────────────────────────────────────
Write-Host "[5/6] Building Tauri desktop app..." -ForegroundColor Yellow

if ($Release) {
    if ($env:TAURI_SIGNING_PRIVATE_KEY) {
        Write-Host "  Signing key detected, building signed release..." -ForegroundColor Green
    } else {
        Write-Host "  WARNING: TAURI_SIGNING_PRIVATE_KEY not set. Updater signatures will fail." -ForegroundColor Yellow
    }
    npm run tauri build
} else {
    npm run tauri build -- --debug
}

# ── Step 6: Report results ───────────────────────────────────────────
Write-Host ""
Write-Host "[6/6] Build complete!" -ForegroundColor Green
Write-Host ""

$bundleDir = "$ROOT\frontend\src-tauri\target\release\bundle"
if ($Release -and (Test-Path $bundleDir)) {
    Write-Host "Output files:" -ForegroundColor Cyan
    Get-ChildItem -Recurse "$bundleDir\nsis\*setup*", "$bundleDir\msi\*.msi" -ErrorAction SilentlyContinue | ForEach-Object {
        $sizeMB = [math]::Round($_.Length / 1MB, 1)
        Write-Host "  $($_.Name) ($sizeMB MB)" -ForegroundColor White
    }
    Get-ChildItem -Recurse "$bundleDir\nsis\*.sig", "$bundleDir\msi\*.sig" -ErrorAction SilentlyContinue | ForEach-Object {
        Write-Host "  $($_.Name) (signature)" -ForegroundColor DarkGray
    }
}

Write-Host ""
Write-Host "Done! To install, run the setup file from:" -ForegroundColor Cyan
Write-Host "  $bundleDir" -ForegroundColor White
