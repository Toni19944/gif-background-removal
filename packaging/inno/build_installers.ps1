param(
  [string]$IsccPath = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
  [string]$IssPath  = "$(Join-Path $PSScriptRoot "installer.iss")"
)

$ErrorActionPreference = "Stop"

Write-Host "== GIF Background Removal: Build installers (CPU + GPU) ==" -ForegroundColor Cyan

# Resolve paths
$IsccPath = (Resolve-Path $IsccPath).Path
$IssPath  = (Resolve-Path $IssPath).Path

if (-not (Test-Path $IsccPath)) {
  throw "ISCC.exe not found at: $IsccPath`nInstall Inno Setup 6, or pass -IsccPath <path to ISCC.exe>"
}

if (-not (Test-Path $IssPath)) {
  throw ".iss not found at: $IssPath"
}

# Sanity-check PyInstaller output folders (relative to repo root)
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$cpuDir = Join-Path $repoRoot "dist\cpu\gif-background-removal"
$gpuDir = Join-Path $repoRoot "dist\gpu\gif-background-removal"

if (-not (Test-Path $cpuDir)) {
  throw "CPU dist folder missing: $cpuDir`nRun the PyInstaller CPU build first (Step 2)."
}
if (-not (Test-Path $gpuDir)) {
  throw "GPU dist folder missing: $gpuDir`nRun the PyInstaller GPU build first (Step 3)."
}

Write-Host "Repo root: $repoRoot"
Write-Host "Using ISCC: $IsccPath"
Write-Host "Using ISS : $IssPath"
Write-Host ""

function Build-Variant([string]$Variant) {
  Write-Host "---- Building installer: $Variant ----" -ForegroundColor Yellow
  & $IsccPath $IssPath "/DVariant=$Variant" | ForEach-Object { Write-Host $_ }
  if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup failed for Variant=$Variant (exit code $LASTEXITCODE)"
  }
  Write-Host "OK: $Variant installer built." -ForegroundColor Green
  Write-Host ""
}

Build-Variant "CPU"
Build-Variant "GPU"

$outDir = Join-Path $PSScriptRoot "Output"
Write-Host "All done!" -ForegroundColor Cyan
Write-Host "Installers should be in: $outDir"