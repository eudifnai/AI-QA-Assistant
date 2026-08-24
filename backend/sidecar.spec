from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules


ROOT = Path(SPECPATH).resolve().parent
grpc_datas, grpc_binaries, grpc_hidden = collect_all("grpc_tools")

analysis = Analysis(
    [str(ROOT / "backend" / "app" / "desktop.py")],
    pathex=[str(ROOT)],
    binaries=grpc_binaries,
    datas=[
        (str(ROOT / "backend" / "migrations"), "backend/migrations"),
        *grpc_datas,
    ],
    hiddenimports=[
        *grpc_hidden,
        *collect_submodules("keyring.backends"),
        "uvicorn.lifespan.on",
        "uvicorn.logging",
        "uvicorn.loops.auto",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets.auto",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(analysis.pure)

executable = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="ai-qa-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
bundle = COLLECT(
    executable,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="ai-qa-backend",
)
