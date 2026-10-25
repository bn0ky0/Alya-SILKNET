param(
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot

$Executable = Join-Path $ProjectRoot "dist\SILKNET\SILKNET.exe"
if (-not $SkipBuild -and -not (Test-Path -LiteralPath $Executable)) {
    & (Join-Path $PSScriptRoot "build_windows.ps1")
    if ($LASTEXITCODE -ne 0) {
        throw "The application build failed with exit code $LASTEXITCODE."
    }
}
if (-not (Test-Path -LiteralPath $Executable)) {
    throw "The application build is missing at $Executable. Run scripts\build_windows.ps1 first."
}

function Find-InnoCompiler {
    $Candidates = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 5\ISCC.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
        (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe")
    )
    foreach ($Candidate in $Candidates) {
        if ($Candidate -and (Test-Path -LiteralPath $Candidate)) {
            return $Candidate
        }
    }

    $RegistryKeys = @(
        "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1",
        "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1",
        "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1"
    )
    foreach ($Key in $RegistryKeys) {
        $InstallLocation = (Get-ItemProperty -LiteralPath $Key -ErrorAction SilentlyContinue).InstallLocation
        if ($InstallLocation) {
            $Candidate = Join-Path $InstallLocation "ISCC.exe"
            if (Test-Path -LiteralPath $Candidate) {
                return $Candidate
            }
        }
    }

    $Command = Get-Command iscc.exe -ErrorAction SilentlyContinue
    if ($Command) {
        return $Command.Source
    }
    return $null
}

$Iscc = Find-InnoCompiler
if (-not $Iscc) {
    throw @"
Inno Setup 6 was not found.

Install it for the current user, then run this script again:

    winget install --id JRSoftware.InnoSetup -e --scope user

Or download it from https://jrsoftware.org/isinfo.php.
"@
}

$Version = "0.1.2"
$Pyproject = Get-Content -LiteralPath (Join-Path $ProjectRoot "pyproject.toml") -Raw
$VersionMatch = [regex]::Match($Pyproject, '(?m)^version\s*=\s*"([^"]+)"')
if ($VersionMatch.Success) {
    $Version = $VersionMatch.Groups[1].Value
}

$OutputDirectory = Join-Path $ProjectRoot "dist\installer"
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null

& $Iscc "/DMyAppVersion=$Version" (Join-Path $PSScriptRoot "installer.iss")
if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup failed with exit code $LASTEXITCODE."
}

$Installer = Join-Path $OutputDirectory "installer.exe"
if (-not (Test-Path -LiteralPath $Installer)) {
    throw "Inno Setup finished without creating $Installer."
}

Write-Host "SILKNET installer is ready: $Installer"
