param(
    [string]$Version = "0.1.0"
)

$ErrorActionPreference = "Stop"

# Build the executable without downloading the large local Transcription engine.
uv run --with pyinstaller pyinstaller --noconfirm --clean packaging/windows/Vellum.spec

if (-not (Get-Command iscc -ErrorAction SilentlyContinue)) {
    throw "Inno Setup (iscc.exe) is required to build the Windows installer."
}

iscc "/DMyAppVersion=$Version" packaging/windows/Vellum.iss
Write-Host "Created dist/installer/Vellum-$Version-setup.exe"
