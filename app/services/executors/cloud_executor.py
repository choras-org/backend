from venv import logger

import paramiko
from typing import Any, Dict
from .simulation_executor_interface import SimulationExecutor
import uuid
import os
from pathlib import Path
import docker
import json
paramiko.util.log_to_file("paramiko.log", level="DEBUG")

# def get_host_path_for_container_path(container_path: str) -> str:
#         """
#         Looks up the host path for a given container path by inspecting
#         the current container's own mounts via the Docker socket.
#         """
#         try:
#             client = docker.from_env()
#             import socket
#             hostname = socket.gethostname()
#             container = client.containers.get(hostname)
#             for mount in container.attrs["Mounts"]:
#                 destination = mount.get("Destination", "")
#                 if container_path.startswith(destination):
#                     host_source = mount["Source"]
#                     relative = os.path.relpath(container_path, destination)
#                     return os.path.join(host_source, relative).replace("\\", "/")
#         except Exception as e:
#             logger.error(f"Could not resolve host path for {container_path}: {e}")
            
#         raise RuntimeError(f"No mount found covering container path: {container_path}")

def get_filenames(json_path):
    """Update msh_path and geo_path in the JSON to only the file name."""
    with open(json_path, "r") as f:
        data = json.load(f)
    if "msh_path" in data:
        data["msh_path"] = Path(data["msh_path"]).name
    if "geo_path" in data:
        data["geo_path"] = Path(data["geo_path"]).name
    with open(json_path, "w") as f:
        json.dump(data, f, indent=4)
    return data["msh_path"], data["geo_path"]

def get_local_file_path(json_path, filename):
    """Get the local path for a file in the same directory as the JSON."""
    return os.path.join(os.path.dirname(json_path), filename)

def get_remote_file_path(image_name, job_id, filename):
    """Get the remote path for a file inside the singularity image."""
    return f"{image_name}_sif_{job_id}/app/{filename}"
    
    

class CloudExecutor(SimulationExecutor):
    
    def __init__(self, hostname, username, password=None, key_path=None, remote_work_dir="/app"):
        self.hostname = hostname
        self.username = username
        self.password = password
        self.key_path = key_path
        self.remote_work_dir = remote_work_dir
        self.ssh_client = None


    def _connect(self):
        self.ssh_client = paramiko.SSHClient()
        self.ssh_client.load_system_host_keys()
        self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        try:
            connect_kwargs = {
                "hostname": self.hostname,
                "username": self.username,
                "look_for_keys": True,
                "allow_agent": True,
            }
            if self.key_path:
                connect_kwargs["key_filename"] = self.key_path
                connect_kwargs["allow_agent"] = False
                connect_kwargs["look_for_keys"] = False
            if self.password:
                connect_kwargs["password"] = self.password
            self.ssh_client.connect(**connect_kwargs)
            print(f"SSH connection established to {self.hostname} as {self.username}")

        except Exception as e:
            print(f"Error while connecting SSH: {e}")


    def upload_file_via_sftp(self, local_path, remote_path):
        
        try:
            if self.ssh_client is None:
                raise RuntimeError("SSH client is not connected. Call _connect() first.")
            sftp = self.ssh_client.open_sftp()
            sftp.put(local_path, remote_path)
            sftp.close()
        except Exception as e:
            print(f"Error while transfering file via SFTP: {e}")

    def send_input_files_to_singularity_image(self, image_name, job_id, sim_config):

        
    
        self.upload_file_via_sftp(container_json_path, remote_json_path)

    def build_singularity_image(self, singularity_image_name="sif_sandbox", image_tar_name=None):
            
        try:
            build_cmd = f"singularity build --sandbox {singularity_image_name} docker-archive://{image_tar_name}"
            stdin, stdout, stderr = self.ssh_client.exec_command(build_cmd)
            build_output = stdout.read().decode()
            build_error = stderr.read().decode()
            print(f"Singularity build_output: {build_output}")
            print(f"Singularity build_error: {build_error}")
        except Exception as e:
            print(f"Error while building singularity image: {e}")


    


    def execute_singularity_image(self, singularity_image_name="sif_sandbox", input_json = "exampleInput_DG.json"):
            
        try:
            #this need to be refactored!!!!!  
            run_cmd = f"singularity exec -w --pwd /app --env JSON_PATH=/app/{input_json} {singularity_image_name} python DGinterface.py"
            #this need to be refactored!!!!! Then test DE as well
            
            stdin, stdout, stderr = self.ssh_client.exec_command(run_cmd)
            run_output = stdout.read().decode()
            run_error = stderr.read().decode()
            print(f"Singularity image execution run_output: {run_output}")
            print(f"Singularity image execution run_error: {run_error}")
        except Exception as e:
            print(f"Error while executing singularity image: {e}")

    def execute(self, method_config: Dict[str, Any], sim_config: Dict[str, Any]):

        self._connect()

        job_id = str(uuid.uuid4())
        image_name = method_config["container_image"].split(":")[0]  # Docker image name without the :latest tag
        tar_image_name = image_name + ".tar"
        local_tar_image_path = os.path.join(os.path.dirname(__file__), tar_image_name)

        self.upload_file_via_sftp(local_tar_image_path, tar_image_name)
        self.build_singularity_image(image_name + "_sif_" + job_id, tar_image_name)   


        #tranfer the input json, geo and msh files into the singularity image
        env = sim_config.get("env", {})
        container_json_path = env.get("JSON_PATH")
        json_filename = Path(container_json_path).name
        msh_filename, geo_filename = get_filenames(container_json_path)

        remote_json_path = get_remote_file_path(image_name, job_id, json_filename)
        remote_msh_path = get_remote_file_path(image_name, job_id, msh_filename)
        remote_geo_path = get_remote_file_path(image_name, job_id, geo_filename)

        self.upload_file_via_sftp(container_json_path, remote_json_path)
        self.upload_file_via_sftp(get_local_file_path(container_json_path, msh_filename), remote_msh_path)
        self.upload_file_via_sftp(get_local_file_path(container_json_path, geo_filename), remote_geo_path)

        self.execute_singularity_image(singularity_image_name=image_name + "_sif_" + job_id, input_json=json_filename)


        #add logic if build fail to not continue
