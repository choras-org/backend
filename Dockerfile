# Default to amd64 because some runtime wheels (e.g. gmsh) and the native
# CGAL build target only ship x86_64 Linux artifacts. Override with
# `--build-arg BUILD_PLATFORM=...` if you really need another arch.
ARG BUILD_PLATFORM=linux/amd64
FROM --platform=${BUILD_PLATFORM} python:3.11.13-slim AS base
WORKDIR /app

# Runtime dependencies (keep minimal)
# libglu1-mesa / libgl1 / libxrender1 / libxcursor1 / libxft2 / libxinerama1:
# the gmsh Python wheel dynamically links against OpenGL/GLU + X11 libs even
# for headless meshing, so they must be present or `import gmsh` fails with
# "libGLU.so.1: cannot open shared object file".
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        postgresql-client \
        git \
        libglu1-mesa \
        libgl1 \
        libgomp1 \
        libxrender1 \
        libxcursor1 \
        libxft2 \
        libxinerama1 && \
    apt-get clean && rm -rf /var/lib/apt/lists/* /var/cache/apt/*

# Upgrade pip and install build dependencies
RUN pip install --upgrade pip setuptools wheel

COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source code (context is the repo root, so scope to backend/)
COPY backend /app
# Copy the geometry-pipeline submodule so the final stage can install it
COPY geometry-pipeline /app/geometry-pipeline

# Make entrypoint executable
RUN sed -i 's/\r$//' ./entrypoint.sh && chmod +x ./entrypoint.sh

# Optional: Build native detector in a builder stage and copy the binary
ARG BUILD_PLATFORM=linux/amd64
FROM --platform=${BUILD_PLATFORM} python:3.11.13-slim AS builder
WORKDIR /build

# Install build tools and native deps for CGAL/Eigen
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        cmake \
        git \
        libcgal-dev \
        libeigen3-dev && \
    apt-get clean && rm -rf /var/lib/apt/lists/* /var/cache/apt/*

# Copy repository and run the native build script for geom_pipeline
COPY . /src
# Note: the submodule repo is named 'geom_pipeline' but the Python package is 'geometry-pipeline'.
WORKDIR /src/geometry-pipeline/src/geometry-pipeline/volume/_native
# Normalize potential Windows CRLF line endings so the shebang works on Linux.
RUN sed -i 's/\r$//' build.sh
RUN chmod +x build.sh || true
RUN ./build.sh
# Ensure the built binary is available at /src/bin/volume_detector so the final
# stage can reliably copy it. The package's build script places the binary in
# /src/geometry-pipeline/bin; copy it to the shared /src/bin path used below.
RUN mkdir -p /src/bin \
    && cp /src/geometry-pipeline/bin/volume_detector /src/bin/volume_detector || true

FROM base AS final
WORKDIR /app

# Runtime shared libraries the native detector links against.
# CGAL's exact arithmetic uses GMP/MPFR, so these must be present at runtime
# even though CGAL itself is largely header-only (compiled into the binary).
RUN apt-get update && \
    apt-get install -y --no-install-recommends libgmp10 libmpfr6 && \
    apt-get clean && rm -rf /var/lib/apt/lists/* /var/cache/apt/*

# Copy compiled native binary if present
COPY --from=builder /src/bin/volume_detector /app/bin/volume_detector

# Expose environment variable pointing to the detector binary path
ENV VOLUME_DETECTOR_BIN=/app/bin/volume_detector

# Install the geom_pipeline package from the submodule present in the
# build context. The repository root is copied into the image at /app in the
# base stage, so install from that location (idempotent when unchanged).
RUN if [ -d "/app/geometry-pipeline" ]; then pip install --no-cache-dir /app/geometry-pipeline; fi

EXPOSE 5001
CMD ["/app/entrypoint.sh"]