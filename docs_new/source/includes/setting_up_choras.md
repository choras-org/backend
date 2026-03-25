# How to Set Up the CHORAS System?

This is the public repository for the **Community Hub for Open-source Room Acoustics Software**. Follow the steps described below.

---

## Git Repo Setup

### Git Installation

Install the latest version of Git from:
[https://git-scm.com/downloads](https://git-scm.com/downloads)

Follow the installer's default settings.

### Repository Cloning

In your terminal:

```bash
git clone <repository-link>
cd CHORAS
```

This repository includes three submodules:

- `frontend-v2`
- `backend`
- `simulation-backend`

If you only want to use the Docker setup (recommended for running CHORAS locally), you do not need to touch these submodules manually. In that case, just follow the Docker-based instructions.

If you want to:

- Explore the underlying code, or
- Run simulations on the cloud

then initialize the submodules:

```bash
git submodule update --init --recursive
```

---

## Docker Setup

> ⚠️ If you're on Windows and unsure whether you need `amd64` or `arm64`, go to **Settings → System → About**. It will say *"x64-based processor"* for AMD, or *"ARM-based processor"* for an ARM chip.

1. Install Docker using the default settings.
2. Open **Docker Desktop** (the application must be running for CHORAS to work).
3. When prompted to sign in/up, click **Continue without signing up** or **Skip**.
4. If Docker Desktop tells you that WSL needs updating, click **Restart**.  
   If this doesn't work, open your terminal and run:

   ```bash
   wsl --update
   ```

5. Once Docker is running, you can continue with the next step.

---

## Cloud Connection Setup

> **This step is only required** if you want to offload heavy simulations to HPC clusters (e.g., SURF Cloud).  
> You can skip this section if you do not have cloud access yet. If you gain access later, come back and complete these steps.

### SSH Key Setup

Generate and configure an SSH key on your machine following the GitHub guide:  
[https://docs.github.com/en/authentication/connecting-to-github-with-ssh/generating-a-new-ssh-key-and-adding-it-to-the-ssh-agent](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/generating-a-new-ssh-key-and-adding-it-to-the-ssh-agent)

> **Do not use a passphrase** when generating your ssh key. There is currently no way for users to enter passphrases in the frontend, although the backend is compatible with them.


In the root directory of the CHORAS repository, open `docker-compose.yml`.  
Add the path to your local SSH key directory in volumes of backend:

```yaml
platform: linux/amd64
build:
  context: . # root of CHORAS
  dockerfile: backend/Dockerfile
ports:
  - "5001:5001"
env_file:
  - .env.api
depends_on:
  - db_service
  - redis
volumes:
  - /var/run/docker.sock:/var/run/docker.sock
  - ./uploads:/app/uploads
  - ./simulation-backend:/app/simulation-backend
  - <absolute-path-ssh-directory>:/root/.ssh:ro # Add this line
```

### Cloud Configuration

After SSH is configured and you receive your cloud access details (IP address, username, etc.):

0. Connect to the cloud directly via the terminal using SSH, using the following command:
   ```bash
   ssh <your_username>@<cloud-ip>
   ```
   This is necessary to add the host to your list of known hosts; without this, CHORAS will not be able to connect to the cloud.
   When connecting for the first time, you will be prompted with something like:
   ```bash
      The authenticity of host 'example.com (192.168.1.1)' can't be established.
      ED25519 key fingerprint is SHA256:abc123...
      Are you sure you want to continue connecting (yes/no/[fingerprint])?  
   ```
   Type in "yes" to continue. Your computer might not have the ssh client installed by default; if this is the case, refer to this guide for how to install it: [https://gist.github.com/bityob/419ca30a766817640e717800b63d6862](https://gist.github.com/bityob/419ca30a766817640e717800b63d6862)


1. Go to the backend submodule:

   ```bash
   cd backend
   ```

2. Open `config.py` and update the `CloudConfig` class at the end of the file:

   ```python
   class CloudConfig:
       """
       Cloud Configuration
       """
       CLOUD_EXECUTOR_HOST = "111.22.333.444"                       # ← Update with your cloud IP
       CLOUD_EXECUTOR_USER = "your_username"                        # ← Update with your username
       CLOUD_STORAGE_PATH = "/path/to/your/files"                   # ← Update with your remote working directory
       CLOUD_EXECUTOR_KEY_PATH = f"{Path.home()}/.ssh/id_ed25519"   # ← Change to a different key name if needed (default is id_ed25519, but it could be id_rsa, etc.)

       CLOUD_EXECUTOR_DIRECTORY = f"/{CLOUD_STORAGE_PATH}/{CLOUD_EXECUTOR_USER}"
   ```

3. In the `CloudConfig` class, update:
   - The **IP address** of the cloud
   - The **username**
   with the values provided by your cloud/HPC provider (e.g., SURF)
   - The **path to your remote files** (this folder will be created if it does not already exist)
   - The **name of your ssh key**. It defaults to `id_ed25519`, but it is possible to change this if you use another key.

  .

> For Cloud/HPC use, `Singularity` should be installed on it. See the following guide for how to do this: https://docs.sylabs.io/guides/3.0/user-guide/installation.html 

---

## Running CHORAS

From the root directory of the CHORAS repository:

1. Make sure **Docker Desktop** is running.
2. In a terminal, run:

   ```bash
   ./CHORAS_BUILD.sh
   ```

   This script builds and starts all required containers.

3. Once the build completes, open your browser and go to:  
   [http://localhost:5173/](http://localhost:5173/)

You should now see the CHORAS user interface.
