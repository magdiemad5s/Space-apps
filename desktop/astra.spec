# -*- mode: python ; coding: utf-8 -*-
"""Freeze the existing inference service, local Node server and Angular build.

Run desktop/build_windows.ps1; this file deliberately contains no training step.
"""
from pathlib import Path

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
    copy_metadata,
)

desktop = Path(SPECPATH).resolve()
project = desktop.parent
resources = desktop / "build" / "resources"
for relative in (
    "frontend/index.html",
    "backend/server.js",
    "backend/node_modules/express/package.json",
    "node/node.exe",
    "model/bundle.joblib",
    "model/inference_manifest.json",
    "fixtures/synthetic_daily_sequence.json",
):
    if not (resources / relative).is_file():
        raise FileNotFoundError(f"Missing staged bundle input: {relative}")


def runtime_module(name):
    return not any(part in {"tests", "testing", "benchmarks"} for part in name.split("."))


hiddenimports = [
    "astra_shield_ml.api",
    "astra_shield_ml.service",
    "astra_shield_ml.features",
    "astra_shield_ml.estimators",  # Classes restored by the trusted joblib pickle.
    "uvicorn.logging",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
]
datas = [(str(resources), "resources")]
binaries = []

# A pickle refers to estimator implementations without ordinary Python imports.
# Include sklearn's compiled estimators and SHAP's native extensions.
# The deployment export excludes unused research XGBoost memory snapshots;
# none of the five selected fitted models uses XGBoost.
# SHAP 0.54.1 does not require numba or llvmlite.
for package in ("sklearn", "shap"):
    hiddenimports += collect_submodules(package, filter=runtime_module, on_error="warn once")
    datas += collect_data_files(package, excludes=["**/tests/**", "**/benchmarks/**"])
for package in ("numpy", "scipy", "sklearn", "shap"):
    binaries += collect_dynamic_libs(package)

# Preserve version metadata and the wheel's embedded license files. Built-in and
# contrib hooks collect additional DLLs, BLAS/OpenMP runtimes and package data.
for distribution in (
    "numpy", "pandas", "scipy", "scikit-learn", "joblib", "threadpoolctl",
    "fastapi", "starlette", "pydantic", "pydantic_core", "uvicorn", "httpx",
    "shap", "slicer", "cloudpickle", "tqdm", "packaging",
):
    datas += copy_metadata(distribution)

a = Analysis(
    [str(desktop / "runtime.py")],
    pathex=[str(project / "ai")],
    binaries=binaries,
    datas=datas,
    hiddenimports=sorted(set(hiddenimports)),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "IPython", "jupyter", "pytest", "xgboost"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ASTRA-SHIELD",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    uac_admin=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="ASTRA-SHIELD",
)
