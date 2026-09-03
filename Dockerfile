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
    libfreetype6-dev  \
    libgl1-mesa-dev \
    libocct-foundation-dev \
    libocct-data-exchange-dev

RUN pip install --upgrade pip

# Copy backend source code
COPY backend/ /app
RUN pip install --no-cache-dir .

# Make entrypoint executable
RUN chmod +x ./entrypoint.sh
EXPOSE 5001
CMD ["/app/entrypoint.sh"]
