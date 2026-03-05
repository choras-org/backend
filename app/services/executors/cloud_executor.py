from venv import logger

import paramiko
from typing import Any, Dict
from .simulation_executor_interface import SimulationExecutor
import uuid
import os
from pathlib import Path
import docker
paramiko.util.log_to_file("paramiko.log", level="DEBUG")

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


    def get_host_path_for_container_path(self, container_path: str) -> str:
        """
        Looks up the host path for a given container path by inspecting
        the current container's own mounts via the Docker socket.
        """
        try:
            client = docker.from_env()
            import socket
            hostname = socket.gethostname()
            container = client.containers.get(hostname)
            for mount in container.attrs["Mounts"]:
                destination = mount.get("Destination", "")
                if container_path.startswith(destination):
                    host_source = mount["Source"]
                    relative = os.path.relpath(container_path, destination)
                    return os.path.join(host_source, relative).replace("\\", "/")
        except Exception as e:
            logger.error(f"Could not resolve host path for {container_path}: {e}")
            
        raise RuntimeError(f"No mount found covering container path: {container_path}")


    def execute_singularity_image(self, singularity_image_name="sif_sandbox"):
            
        try:
            #this need to be refactored!!!!!  
            run_cmd = f"singularity exec -w --pwd /app --env JSON_PATH=/app/exampleInput_DG.json {singularity_image_name} python DGinterface.py"
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

        # tranfer the input json file in o the singularity image
        # env = sim_config.get("env", {})
        # container_json_path = env.get("JSON_PATH")
        # print(f"container_json_path: {container_json_path}")
        # container_uploads_dir = str(Path(container_json_path).parent)
        # print(f"container_uploads_dir: {container_uploads_dir}")
        # host_uploads_dir = self.get_host_path_for_container_path(container_uploads_dir)
        # print(f"host_uploads_dir: {host_uploads_dir}")

        # print(f"Resolved host path: {host_uploads_dir} for container path: {container_uploads_dir}")
        # json_filename = Path(container_json_path).name
        # print(f"json file name: {json_filename}")

        # remote_json_path = f"{image_name}_sif_{job_id}/app/{json_filename}"
        # print(f"remote json path: {remote_json_path}")
        # self.upload_file_via_sftp(container_json_path, remote_json_path)


        self.execute_singularity_image(image_name + "_sif_" + job_id)
