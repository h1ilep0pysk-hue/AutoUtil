# AutoUtil exe build
# Run from the project root (folder with main.py):
#   powershell -ExecutionPolicy Bypass -File build.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# pick the first supported Python: 3.13 or 3.12
$PyVer = $null
foreach ($v in @("-3.13", "-3.12")) {
    & py $v --version *> $null
    if ($LASTEXITCODE -eq 0) { $PyVer = $v; break }
}
if (-not $PyVer) {
    throw "Python 3.12 or 3.13 not found. Install one, reopen PowerShell, and try again."
}
Write-Host "==> using Python via: py $PyVer" -ForegroundColor Cyan

$Venv = ".venv"
if (-not (Test-Path "$Venv\Scripts\python.exe")) {
    Write-Host "==> creating venv" -ForegroundColor Cyan
    & py $PyVer -m venv $Venv
    if ($LASTEXITCODE -ne 0) { throw "venv creation failed" }
}
$VenvPy = "$Venv\Scripts\python.exe"

Write-Host "==> installing dependencies" -ForegroundColor Cyan
& $VenvPy -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed" }
& $VenvPy -m pip install -e ".[dev]"
if ($LASTEXITCODE -ne 0) { throw "project install failed" }
& $VenvPy -m pip install pyinstaller
if ($LASTEXITCODE -ne 0) { throw "pyinstaller install failed" }

Write-Host "==> running tests" -ForegroundColor Cyan
& $VenvPy -m pytest -q
# pytest exit code 5 = no tests collected (the archive has an empty tests/ folder): warn, do not stop
if ($LASTEXITCODE -eq 5) { Write-Host "WARNING: no tests found, continuing" -ForegroundColor Yellow }
elseif ($LASTEXITCODE -ne 0) { throw "tests failed, build stopped" }

Write-Host "==> cleaning old build" -ForegroundColor Cyan
Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
Remove-Item -Force AutoUtil.spec -ErrorAction SilentlyContinue

Write-Host "==> building exe" -ForegroundColor Cyan
& $VenvPy -m PyInstaller --noconfirm --onefile --windowed `
    --name AutoUtil `
    --icon "ui\assets\autoutil.ico" `
    --add-data "ui\assets;ui\assets" `
    --collect-data rapidocr `
    main.py
if ($LASTEXITCODE -ne 0) { throw "pyinstaller failed" }

if (-not (Test-Path "dist\AutoUtil.exe")) { throw "dist\AutoUtil.exe not found" }
$size = [math]::Round((Get-Item "dist\AutoUtil.exe").Length / 1MB, 1)
Write-Host "==> done: dist\AutoUtil.exe ($size MB)" -ForegroundColor Green