# Windows stage
FROM mcr.microsoft.com/windows/servercore:ltsc2022 AS windows
WORKDIR C:/app

COPY requirements.txt C:/app
COPY simulation-backend/ C:/app/simulation-backend
COPY Diffusion/ C:/app/Diffusion
COPY edg-acoustics/ C:/app/edg-acoustics
COPY MyNewMethod/ C:/app/MyNewMethod

RUN python -m pip install --upgrade pip
RUN python -m pip install simulation-backend/. Diffusion/. edg-acoustics/. MyNewMethod/. --no-cache-dir -r requirements.txt

COPY . C:/app
CMD ["powershell", "-File", "C:/app/entrypoint.ps1"]