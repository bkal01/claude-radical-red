FROM python:3.12-slim-bookworm AS build

RUN apt-get update && apt-get install --yes --no-install-recommends \
    build-essential \
    cmake \
    git \
    libavcodec-dev \
    libavfilter-dev \
    libavformat-dev \
    libavutil-dev \
    libedit-dev \
    libpng-dev \
    libswscale-dev \
    libzip-dev \
    pkg-config \
    zipcmp \
    zipmerge \
    ziptool \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir cffi setuptools

RUN git clone --depth=1 --branch 0.10.5 https://github.com/mgba-emu/mgba.git /src/mgba \
    && cmake -S /src/mgba -B /src/mgba/build \
        -DBUILD_PYTHON=ON \
        -DPYTHON_EXECUTABLE=/usr/local/bin/python \
        -DBUILD_SDL=OFF \
        -DBUILD_QT=OFF \
        -DBUILD_LIBRETRO=OFF \
        -DUSE_LUA=OFF \
        -DCMAKE_BUILD_TYPE=Release \
    && cmake --build /src/mgba/build --target mgba-py -j2

RUN mkdir /opt/mgba \
    && cp -R "$(find /src/mgba/build/python -type d -name mgba | head -1)" /opt/mgba/mgba

FROM python:3.12-slim-bookworm

RUN apt-get update && apt-get install --yes --no-install-recommends \
    libavcodec59 \
    libavfilter8 \
    libavformat59 \
    libavutil57 \
    libedit2 \
    libpng16-16 \
    libswscale6 \
    libzip4 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=build /src/mgba/build /src/mgba/build
COPY --from=build /opt/mgba /opt/mgba
COPY rrbench /app/rrbench
COPY data /app/data

RUN pip install --no-cache-dir Pillow cached-property cffi imageio imageio-ffmpeg numpy PyYAML

ENV PYTHONPATH=/app:/opt/mgba
WORKDIR /app
