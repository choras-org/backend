import os
import uuid
import docker
import logging
from typing import Any, Dict
from .simulation_executor_interface import SimulationExecutor
from pathlib import Path

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
            if container_path.startswith(destination):
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
        self._jobs = {}

    def execute(self, method_config: Dict[str, Any], sim_config: Dict[str, Any]) -> tuple:
        image = method_config["container_image"]
        container_name = method_config["container_name"]
        env = sim_config.get("env", {})
        job_id = str(uuid.uuid4())
        command = method_config.get("command")

        # Resolve the container path (e.g. /app/uploads) to the real host path
        # so Docker can mount it into the child container
        container_json_path = env.get("JSON_PATH")
        container_uploads_dir = str(Path(container_json_path).parent)
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
                remove = True,
            )
            self._jobs[job_id] = container
            return job_id, container

        except Exception as e:
            logger.error(f"Failed to start Docker container: {e}")
            raise