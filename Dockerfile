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

COPY requirements.txt /app
COPY simulation-backend/ /app/simulation-backend
COPY Diffusion/ /app/Diffusion
COPY MyNewMethod/ /app/MyNewMethod

RUN pip install --upgrade pip
RUN pip install simulation-backend/.
RUN pip install Diffusion/.
# RUN pip install deeponet-acoustic-wave-prop/.
RUN pip install MyNewMethod/.
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app
RUN chmod +x ./entrypoint.sh
EXPOSE 5001
CMD ["/app/entrypoint.sh"]