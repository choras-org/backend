FROM python:3.11.13-slim
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
    libocct-data-exchange-dev

# Copy requirements and local submodules
COPY backend/requirements.txt /app
COPY simulation-backend/ /app/simulation-backend
COPY backend/MyNewMethod/ /app/MyNewMethod

# Upgrade pip
RUN pip install --upgrade pip

# Install local submodules explicitly
RUN pip install /app/simulation-backend
RUN pip install /app/MyNewMethod

# Install remaining dependencies from requirements.txt, excluding local submodules
RUN grep -vE '^-e\s+(\.\./)?(simulation-backend|MyNewMethod)' requirements.txt > temp_reqs.txt \
    && pip install --no-cache-dir -r temp_reqs.txt

# Copy backend source code
COPY backend/ /app

# Make entrypoint executable
RUN chmod +x ./entrypoint.sh
EXPOSE 5001
CMD ["/app/entrypoint.sh"]
