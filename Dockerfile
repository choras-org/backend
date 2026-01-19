FROM python:3.11.13-slim
WORKDIR /app
RUN apt-get update && \
    apt-get install -y postgresql-client && \
    apt clean && \
    apt-get install -y git && \
    rm -rf /var/cache/apt/* &&\
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

COPY simulation-backend/ /app/simulation-backend

RUN pip install --upgrade pip
RUN pip install --no-cache-dir simulation-backend/.[backends]

COPY . /app
RUN chmod +x ./entrypoint.sh
EXPOSE 5001
CMD ["/app/entrypoint.sh"]
