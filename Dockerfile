FROM python:3.11.13-slim

ENV DEBIAN_FRONTEND=noninteractive

# RUN apt-get update && apt-get install -y --no-install-recommends \
#     build-essential \
#     cmake \
#     git \
#     libocct-data-exchange-dev \
#     libocct-foundation-dev \
#     libocct-modeling-algorithms-dev \
#     libocct-modeling-data-dev \
#     libocct-ocaf-dev \
#     libocct-visualization-dev \
#     liblapack-dev \
#     libblas-dev \
#     libpng-dev \
#     libjpeg-dev \
#     zlib1g-dev \
#     && rm -rf /var/lib/apt/lists/*

# # Clone the latest Gmsh source code
# WORKDIR /tmp
# # RUN git clone --depth 1 https://onelab.info/gmsh/gmsh.git

# RUN git clone --depth 1 --branch gmsh_4_13_1 https://gitlab.onelab.info/gmsh/gmsh.git /tmp/gmsh

# # Configure and compile a headless build with Python bindings
# WORKDIR /tmp/gmsh/build
# RUN cmake .. \
#     -DCMAKE_C_FLAGS="-D_XOPEN_SOURCE=700 -Wno-error=implicit-function-declaration" \
#     -DENABLE_FLTK=OFF \
#     -DENABLE_OPENGL=OFF \
#     -DENABLE_GRAPHICS=OFF \
#     -DENABLE_BUILD_SHARED=ON \
#     -DENABLE_BUILD_DYNAMIC=ON \
#     -DENABLE_WRAP_PYTHON=ON \
#     && make -j$(nproc) \
#     && make install

# # Build and install the Python wheel directly into the Python environment
# # WORKDIR /tmp/gmsh/build/python
# # RUN pip install --no-cache-dir .
# ENV PYTHONPATH="/usr/local/lib"

WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y postgresql-client git && \
    apt clean && \
    rm -rf /var/cache/apt/* && \
    apt-get -y install \
        libglu1 \
        libxcursor-dev \
        libxft2 \
        libxinerama1 \
        libfltk1.3-dev \
        libfreetype6-dev \
        libgl1-mesa-dev \
        libocct-foundation-dev \
        libocct-data-exchange-dev \
        gmsh \
        libgmsh-dev \
        python3-gmsh \
        cmake \
        build-essential

# Add Debian's site-packages to site-packages so pip/Python can find gmsh
# RUN SYS_SITE_PACKAGES=$(python3 -c "import site; print(site.getsitepackages()[0])") && \
#     PIP_SITE_PACKAGES=$(python -c "import site; print(site.getsitepackages()[0])") && \
#     echo "$SYS_SITE_PACKAGES" > "$PIP_SITE_PACKAGES/system-site-packages.pth"

# Make system python3-gmsh available to the pip environment
# This creates a symlink so pip-installed packages can import gmsh
RUN SITE_PACKAGES=$(python -c "import site; print(site.getsitepackages()[0])") && \
    ln -sf /usr/lib/python3/dist-packages/gmsh* "$SITE_PACKAGES/"

# Upgrade pip and install build dependencies
RUN pip install --upgrade pip setuptools wheel

# Copy requirements and local submodules
COPY backend/requirements.txt /app

# Install remaining dependencies from requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source code
COPY backend/ /app

# Make entrypoint executable
RUN chmod +x ./entrypoint.sh
EXPOSE 5001
CMD ["/app/entrypoint.sh"]
