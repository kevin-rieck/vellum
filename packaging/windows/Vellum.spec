# PyInstaller configuration for the user-level Vellum tray executable.
# The large-v3-turbo Transcription engine is intentionally acquired after setup,
# never bundled into this installer.
from pathlib import Path

from PyInstaller.building.build_main import Analysis, COLLECT, EXE, PYZ
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata


ROOT = Path(SPECPATH).resolve().parents[1]
hiddenimports = (
    collect_submodules("pystray")
    + collect_submodules("PIL")
    + collect_data_files("pystray")
)

analysis = Analysis(
    [str(ROOT / "src" / "vellum" / "app.py")],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=[
        (str(ROOT / "LICENSE"), "."),
        (str(ROOT / "README.md"), "."),
        *copy_metadata("vellum"),
    ],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(analysis.pure)
executable = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="vellum",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)
COLLECT(
    executable,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=True,
    name="vellum",
)
