#!/usr/bin/env python3
"""
Build script — creates a standalone executable for the current platform.

Usage:
    python build.py

Requires: pip install pyinstaller pillow
"""

import subprocess
import sys
import platform
import os

APP_NAME = "GraphOverlayPyWR"
SCRIPT   = "graph_overlay_pywr.py"
ICON     = None  # Set to .ico (Windows) or .icns (Mac) path if you have one


def ensure(package):
    try:
        __import__(package)
    except ImportError:
        print(f"Installing {package}...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", package])


def main():
    ensure("PyInstaller")
    ensure("PIL")   # pillow

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--windowed",
        f"--name={APP_NAME}",
        "--clean",
        "--hidden-import=PIL",
        "--hidden-import=PIL.Image",
        "--hidden-import=PIL.ImageTk",
    ]

    os_name = platform.system()
    if os_name == "Darwin":
        print("Building for macOS...")
        cmd.append("--osx-bundle-identifier=com.graphoverlay.pywr")
        if ICON and os.path.exists(ICON):
            cmd.extend(["--icon", ICON])
    elif os_name == "Windows":
        print("Building for Windows...")
        if ICON and os.path.exists(ICON):
            cmd.extend(["--icon", ICON])
    else:
        print(f"Building for {os_name}...")

    cmd.append(SCRIPT)

    print(f"Running: {' '.join(cmd)}\n")
    subprocess.check_call(cmd)

    dist_dir = "dist"
    exe_name = f"{APP_NAME}.exe" if os_name == "Windows" else APP_NAME
    exe_path = os.path.join(dist_dir, exe_name)

    if os.path.exists(exe_path):
        size_mb = os.path.getsize(exe_path) / (1024 * 1024)
        print(f"\n{'='*50}")
        print(f"  BUILD SUCCESSFUL")
        print(f"  Output: {os.path.abspath(exe_path)}")
        print(f"  Size:   {size_mb:.1f} MB")
        print(f"{'='*50}")
    else:
        print("\nBuild completed. Check the dist/ folder for your executable.")


if __name__ == "__main__":
    main()
