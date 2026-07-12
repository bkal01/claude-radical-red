#!/bin/bash
# Rebuild the mgba Python bindings and install them into the project venv.
#
# Run this after a system restart wipes ~/mgba/build, or whenever the compiled
# bindings need refreshing. mgba source lives at ~/mgba (cloned from
# https://github.com/mgba-emu/mgba.git, tag 0.10.5). The build requires ffmpeg
# (brew install ffmpeg) so that EReaderAnchorList symbols are compiled into
# libmgba.dylib.
#
# mgba is wired into the project as a uv path dependency (vendor/mgba, see
# pyproject.toml [tool.uv.sources]). This script rebuilds the compiled package,
# copies it into vendor/mgba/mgba, and lets `uv sync` install it as a normal
# tracked package -- so plain `uv run` / `uv sync` never prune it.
#
# Usage: bash scripts/install_mgba.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
MGBA_SRC=~/mgba
MGBA_BUILD=~/mgba/build
PYTHON="$PROJECT_DIR/.venv/bin/python"
VENDOR_PKG="$PROJECT_DIR/vendor/mgba/mgba"

if [ ! -d "$MGBA_SRC" ]; then
    echo "Cloning mgba 0.10.5..."
    git clone --depth=1 --branch 0.10.5 https://github.com/mgba-emu/mgba.git "$MGBA_SRC"
fi

echo "Configuring..."
cmake -S "$MGBA_SRC" -B "$MGBA_BUILD" \
    -DBUILD_PYTHON=ON \
    -DPYTHON_EXECUTABLE="$PYTHON" \
    -DBUILD_SDL=OFF \
    -DBUILD_QT=OFF \
    -DBUILD_LIBRETRO=OFF \
    -DUSE_LUA=OFF \
    -DCMAKE_BUILD_TYPE=Debug \
    -Wno-dev

echo "Building mgba-py..."
cmake --build "$MGBA_BUILD" --target mgba-py -j"$(sysctl -n hw.logicalcpu)"

LIB_DIR=$(ls -d "$MGBA_BUILD/python/lib."*cpython* | head -1)
echo "Vendoring built package from $LIB_DIR/mgba"
rm -rf "$VENDOR_PKG"
cp -R "$LIB_DIR/mgba" "$VENDOR_PKG"
rm -rf "$VENDOR_PKG/__pycache__"

echo "Installing into venv via uv..."
cd "$PROJECT_DIR"
uv sync --reinstall-package mgba

uv run python -c "import mgba.core; print('mgba OK')"
