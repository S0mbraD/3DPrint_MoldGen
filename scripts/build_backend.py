"""Build the MoldGen Python backend into a standalone executable.

Usage:
    python scripts/build_backend.py

Produces:
    frontend/src-tauri/binaries/moldgen-server-x86_64-pc-windows-msvc.exe
"""

import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST_DIR = ROOT / "dist_backend"
TAURI_BIN = ROOT / "frontend" / "src-tauri" / "binaries"


def get_target_triple() -> str:
    """Rust-style target triple for the current platform."""
    machine = platform.machine().lower()
    system = platform.system().lower()

    arch = {"amd64": "x86_64", "x86_64": "x86_64", "arm64": "aarch64", "aarch64": "aarch64"}.get(
        machine, machine
    )

    if system == "windows":
        return f"{arch}-pc-windows-msvc"
    elif system == "darwin":
        return f"{arch}-apple-darwin"
    else:
        return f"{arch}-unknown-linux-gnu"


def build():
    triple = get_target_triple()
    print(f"[build_backend] Target: {triple}")
    print(f"[build_backend] Python: {sys.executable}")

    DIST_DIR.mkdir(parents=True, exist_ok=True)
    TAURI_BIN.mkdir(parents=True, exist_ok=True)

    pyinstaller_args = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onefile",
        "--name", "moldgen-server",
        "--distpath", str(DIST_DIR),
        "--workpath", str(ROOT / "build_tmp"),
        "--specpath", str(ROOT / "build_tmp"),
        "--hidden-import", "moldgen",
        "--hidden-import", "moldgen.main",
        "--hidden-import", "moldgen.core",
        "--hidden-import", "moldgen.api",
        "--hidden-import", "moldgen.ai",
        "--hidden-import", "moldgen.gpu",
        "--hidden-import", "uvicorn",
        "--hidden-import", "fastapi",
        "--hidden-import", "trimesh",
        "--hidden-import", "numpy",
        "--hidden-import", "scipy",
        "--hidden-import", "pydantic",
        "--hidden-import", "pydantic_settings",
        "--collect-submodules", "moldgen",
        "--collect-submodules", "uvicorn",
        "--collect-data", "trimesh",
        str(ROOT / "scripts" / "_server_entry.py"),
    ]

    print("[build_backend] Running PyInstaller...")
    subprocess.check_call(pyinstaller_args, cwd=str(ROOT))

    src_exe = DIST_DIR / ("moldgen-server.exe" if sys.platform == "win32" else "moldgen-server")
    dst_name = f"moldgen-server-{triple}" + (".exe" if sys.platform == "win32" else "")
    dst = TAURI_BIN / dst_name

    print(f"[build_backend] Copying {src_exe} → {dst}")
    shutil.copy2(src_exe, dst)

    print(f"[build_backend] Done! Binary: {dst}")
    print(f"[build_backend] Size: {dst.stat().st_size / (1024*1024):.1f} MB")


if __name__ == "__main__":
    build()
