#!/bin/bash
# Rebuild and install mgba Python bindings into the project venv.
#
# Run this after any `uv sync`, or after a system restart wipes ~/mgba/build.
# mgba source lives at ~/mgba (cloned from https://github.com/mgba-emu/mgba.git,
# tag 0.10.5). The build requires ffmpeg (brew install ffmpeg) so that
# EReaderAnchorList symbols are compiled into libmgba.dylib.
#
# Usage: bash scripts/install_mgba.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
MGBA_SRC=~/mgba
MGBA_BUILD=~/mgba/build
PYTHON="$PROJECT_DIR/.venv/bin/python"
PTH_FILE="$PROJECT_DIR/.venv/lib/python3.10/site-packages/mgba.pth"

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

LIB_DIR=$(ls -d "$MGBA_BUILD/python/lib."*)
echo "$LIB_DIR" > "$PTH_FILE"
echo "Installed via $PTH_FILE -> $LIB_DIR"

"$PYTHON" -c "import mgba.core; print('mgba OK')"
