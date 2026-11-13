# PlayGo Trading Phase 2 validation (Windows PowerShell)
# Runs checks without requiring GitHub-hosted Actions runners.
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Push-Location $root
try {
    Write-Host "== Python dependency setup ==" -ForegroundColor Cyan
    Push-Location backend
    try {
        py -m pip install -r requirements.txt
        if ($LASTEXITCODE -ne 0) { throw "Backend dependency installation failed" }
        Write-Host "== Python compilation ==" -ForegroundColor Cyan
        py -m compileall -q .
        if ($LASTEXITCODE -ne 0) { throw "Backend syntax compilation failed" }
        Write-Host "== Backend tests ==" -ForegroundColor Cyan
        py -m unittest discover -s . -p "test_*.py" -v
        if ($LASTEXITCODE -ne 0) { throw "Backend unit tests failed" }
    } finally { Pop-Location }
    Write-Host "== Frontend dependency setup ==" -ForegroundColor Cyan
    Push-Location frontend
    try {
        npm ci
        if ($LASTEXITCODE -ne 0) { throw "Frontend dependency installation failed" }
        Write-Host "== TypeScript and Vite build ==" -ForegroundColor Cyan
        npm run build
        if ($LASTEXITCODE -ne 0) { throw "Frontend build failed" }
    } finally { Pop-Location }
    Write-Host "All local static checks and unit tests passed." -ForegroundColor Green
} finally { Pop-Location }
