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
        libxinerama1 \
        libfltk1.3-dev \
        libfreetype6-dev \
        libgl1-mesa-dev \
        libocct-foundation-dev \
        libocct-data-exchange-dev && \
    apt-get clean && rm -rf /var/lib/apt/lists/* /var/cache/apt/*

# Upgrade pip and install build dependencies
RUN pip install --upgrade pip setuptools wheel

# Copy backend source code (context is the repo root, so scope to backend/)
COPY backend /app

# Make entrypoint executable
RUN sed -i 's/\r$//' ./entrypoint.sh && chmod +x ./entrypoint.sh

# Builder: install the backend and its dependencies into a venv. geometry_pipeline
# compiles its native CGAL detector into the package during this install, which
# is the only part that needs a C++ toolchain + CGAL/Eigen headers.
FROM base AS builder

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        libcgal-dev \
        libeigen3-dev && \
    apt-get clean && rm -rf /var/lib/apt/lists/* /var/cache/apt/*

RUN python -m venv /opt/venv && /opt/venv/bin/pip install --no-cache-dir .

FROM base AS final
WORKDIR /app

# Runtime shared libraries the native detector links against.
# CGAL's exact arithmetic uses GMP/MPFR, so these must be present at runtime
# even though CGAL itself is largely header-only (compiled into the binary).
RUN apt-get update && \
    apt-get install -y --no-install-recommends libgmp10 libmpfr6 && \
    apt-get clean && rm -rf /var/lib/apt/lists/* /var/cache/apt/*

# Installed backend + dependencies, including the compiled detector
COPY --from=builder /opt/venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH

# The CMake build skips the detector quietly when CGAL is missing, so fail here.
RUN python -c "from geometry_pipeline.cavity_detection.native_bridge import native_detector_path as p; assert p(), 'volume_detector missing'"

EXPOSE 5001
CMD ["/app/entrypoint.sh"]
