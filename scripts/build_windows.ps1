param([switch]$Console)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot

$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) {
    $PythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($PythonCommand) {
        $Python = $PythonCommand.Source
    } else {
        throw "Python 3.12 or newer was not found. Install Python and the project build extra first."
    }
}

& $Python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)"
if ($LASTEXITCODE -ne 0) {
    throw "SILKNET requires Python 3.12 or newer to build."
}

& $Python -m PyInstaller --version *> $null
if ($LASTEXITCODE -ne 0) {
    throw 'PyInstaller is missing. Run: python -m pip install -e ".[build]"'
}

$WindowMode = if ($Console) { "--console" } else { "--windowed" }
$AssetSource = Join-Path $ProjectRoot "src\silknet\assets"
$IconFile = Join-Path $AssetSource "alya.ico"

if (-not (Test-Path -LiteralPath $AssetSource)) {
    throw "Bundled assets were not found at $AssetSource."
}
if (-not (Test-Path -LiteralPath $IconFile)) {
    throw "Application icon was not found at $IconFile."
}

& $Python -m PyInstaller `
    --noconfirm `
    --clean `
    $WindowMode `
    --name SILKNET `
    --paths (Join-Path $ProjectRoot "src") `
    --collect-submodules silknet `
    --add-data "$AssetSource;silknet\assets" `
    --icon "$IconFile" `
    --distpath (Join-Path $ProjectRoot "dist") `
    --workpath (Join-Path $ProjectRoot "build") `
    (Join-Path $ProjectRoot "src\silknet\__main__.py")

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE."
}

$Executable = Join-Path $ProjectRoot "dist\SILKNET\SILKNET.exe"
if (-not (Test-Path -LiteralPath $Executable)) {
    throw "PyInstaller finished without creating $Executable."
}

$QtDirectory = (& $Python -c "from pathlib import Path; import PySide6; print(Path(PySide6.__file__).resolve().parent)").Trim()
if (-not (Test-Path -LiteralPath (Join-Path $QtDirectory "icuuc.dll"))) {
    # The Windows wheel uses system ICU; discard unrelated copies discovered on PATH.
    $InternalDirectory = Join-Path (Split-Path -Parent $Executable) "_internal"
    Get-ChildItem -LiteralPath $InternalDirectory -Recurse -File |
        Where-Object { $_.Name -match '^icu(uc|in|dt\d+)\.dll$' } |
        ForEach-Object { [System.IO.File]::Delete($_.FullName) }
}

Write-Host "SILKNET build is ready: $Executable"
