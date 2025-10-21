# Use Buildx ARG to pick base image based on target OS
ARG TARGETOS
FROM python:3.11.13-slim AS linux
FROM mcr.microsoft.com/windows/servercore:ltsc2022 AS windows

# Select the correct base image
FROM ${TARGETOS:-linux} AS base

# Set workdir
WORKDIR /app

# Install dependencies conditionally
# Linux-only
RUN if [ "$TARGETOS" = "linux" ]; then \
      apt-get update && \
      apt-get install -y postgresql-client git \
                         libglu1 libxcursor-dev libxft2 libxinerama1 \
                         libfltk1.3-dev libfreetype6-dev libgl1-mesa-dev \
                         libocct-foundation-dev libocct-data-exchange-dev && \
      apt-get clean && rm -rf /var/lib/apt/lists/* ; \
    fi

# Windows-only (example: install git via choco if needed)
RUN if [ "$TARGETOS" = "windows" ]; then \
      powershell -Command "Set-ExecutionPolicy Bypass -Scope Process -Force; \
                           iex ((New-Object System.Net.WebClient).DownloadString('https://chocolatey.org/install.ps1'));" ; \
    fi

# Common environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8

# Copy Python packages
COPY requirements.txt /app
COPY simulation-backend/ /app/simulation-backend
COPY Diffusion/ /app/Diffusion
COPY edg-acoustics/ /app/edg-acoustics
COPY MyNewMethod/ /app/MyNewMethod

# Install Python packages
RUN pip install --upgrade pip && \
    pip install simulation-backend/. && \
    pip install Diffusion/. && \
    pip install edg-acoustics/. && \
    pip install MyNewMethod/. && \
    pip install --no-cache-dir -r requirements.txt

# Copy the rest of the app
COPY . /app

# Chmod entrypoint on Linux only
RUN if [ "$TARGETOS" = "linux" ]; then chmod +x ./entrypoint.sh; fi

# Expose port
EXPOSE 5001

# Entry point (Windows or Linux)
CMD if [ "$TARGETOS" = "linux" ]; then /app/entrypoint.sh; else powershell -File C:/app/entrypoint.ps1; fi
