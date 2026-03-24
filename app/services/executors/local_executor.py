import os
import uuid
import docker
import logging
from typing import Any, Dict
from .simulation_executor_interface import SimulationExecutor
from pathlib import Path
from flask_smorest import abort
import json
from app.services import model_service, file_service

logger = logging.getLogger(__name__)


def get_host_path_for_container_path(container_path: str) -> str:
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
            if destination == container_path:
                host_source = mount["Source"]
                relative = os.path.relpath(container_path, destination)
                return os.path.join(host_source, relative).replace("\\", "/")
    except Exception as e:
        logger.error(f"Could not resolve host path for {container_path}: {e}")
        raise

    raise RuntimeError(f"No mount found covering container path: {container_path}")


class LocalExecutor(SimulationExecutor):
    def __init__(self, work_dir=None):
        if work_dir is None:
            work_dir = os.getenv("DOCKER_WORK_DIR", "/app")
        self.work_dir = work_dir

    def _get_container_name(self, method_config: Dict[str, Any]) -> str:
        simulation_method = method_config["simulation_method"]
        simulation_id = method_config["simulation_id"]
        return f"choras-{simulation_method}-simulation-{simulation_id}"

    def execute(self, method_config: Dict[str, Any], sim_config: Dict[str, Any]) -> tuple:
        
        image = method_config["container_image"]
        container_name = self._get_container_name(method_config)
        env = sim_config.get("env", {})

        # Resolve the container path (e.g. /app/uploads) to the real host path
        # so Docker can mount it into the child container
        container_json_path = env.get("JSON_PATH")
        container_uploads_dir = str(Path(container_json_path).parent)
        print(f"Container uploads dir: {container_uploads_dir}")
        host_uploads_dir = get_host_path_for_container_path(container_uploads_dir)

        logger.info(f"Resolved host path: {host_uploads_dir} for container path: {container_uploads_dir}")

        try:
            client = docker.from_env()
            container = client.containers.run(
                image=image,
                environment=env,  # JSON_PATH is the container path, valid in child too
                volumes={
                    host_uploads_dir: {
                        "bind": container_uploads_dir,  # same path in child container
                        "mode": "rw",
                    }
                },
                detach=True,
                working_dir=self.work_dir,
                name=container_name,
                # name=f"simjob_{job_id[:8]}",
                # remove = True,
            )
            return container

        except Exception as e:
            logger.error(f"Failed to start Docker container: {e}")
            raise
    
    def cancel(self, cancelation_info: Dict[str, Any]):
        """Cancel a running Docker container by its container name."""
        container_name = self._get_container_name(cancelation_info)
        try:
            client = docker.from_env()
            container = client.containers.get(container_name)
            container.kill()
            container.remove()
            logger.info(f"Killed and removed container: {container_name}")
        except docker.errors.NotFound:
            logger.error(f"Container {container_name} not found (already stopped)")
        except Exception as e:
            logger.error(f"Failed to kill container {container_name}: {e}")