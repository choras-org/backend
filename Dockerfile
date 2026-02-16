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

# COPY files relative to repo root
COPY backend/requirements.txt /app
COPY simulation-backend/ /app/simulation-backend
COPY backend/MyNewMethod/ /app/MyNewMethod

# Install Python dependencies
RUN pip install --upgrade pip
RUN pip install simulation-backend/.
RUN pip install MyNewMethod/.
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY backend/ /app

RUN chmod +x ./entrypoint.sh
EXPOSE 5001
CMD ["/app/entrypoint.sh"]
