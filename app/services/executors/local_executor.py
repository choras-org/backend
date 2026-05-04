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


def _is_running_in_container() -> bool:
    """Return True when the current process appears to be running inside a container."""
    if os.path.exists("/.dockerenv") or os.path.exists("/run/.containerenv"):
        return True

    cgroup_paths = ["/proc/self/cgroup", "/proc/1/cgroup"]
    keywords = ("docker", "containerd", "kubepods", "podman", "lxc")

    for path in cgroup_paths:
        if not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as handle:
                contents = handle.read()
        except OSError:
            continue
        if any(keyword in contents for keyword in keywords):
            return True

    return False


def _get_current_container(client):
    """Return the Docker container object for the current container."""
    import socket

    hostname = socket.gethostname()
    try:
        return client.containers.get(hostname)
    except docker.errors.NotFound:
        for container in client.containers.list(all=True):
            if hostname == container.name or hostname in container.id:
                return container
        raise


def get_host_path_for_container_path(container_path: str) -> str:
    """
    Resolves the host path corresponding to a given container path by inspecting
    the current container's mounts using the Docker socket.

    For local debugging (not in a container), returns the container_path as-is.

    Args:
        container_path (str): The absolute path inside the container to resolve.

    Returns:
        str: The corresponding absolute path on the host machine (or container_path if local).

    Raises:
        RuntimeError: If no mount is found covering the given container path (in container only).
        Exception: If there is an error communicating with Docker or resolving the path (in container only).
    """
    if not _is_running_in_container():
        logger.warning(
            f"Running locally (not in container). Returning container_path as-is: {container_path}"
        )
        return container_path

    try:
        client = docker.from_env()
        container = _get_current_container(client)
        container_path = os.path.normpath(container_path)

        best_mount = None
        best_destination = None
        for mount in container.attrs.get("Mounts", []):
            destination = mount.get("Destination")
            if not destination:
                continue
            destination = os.path.normpath(destination)
            if (
                container_path == destination
                or destination == os.sep
                or container_path.startswith(destination + os.sep)
            ):
                if best_destination is None or len(destination) > len(best_destination):
                    best_mount = mount
                    best_destination = destination

        if best_mount is None:
            raise RuntimeError(
                f"No mount found covering container path: {container_path}"
            )

        host_source = best_mount["Source"]
        relative = os.path.relpath(container_path, best_destination)
        if relative == ".":
            return host_source.replace("\\", "/")
        return os.path.join(host_source, relative).replace("\\", "/")

    except Exception as e:
        logger.error(f"Could not resolve host path for {container_path}: {e}")
        raise


class LocalExecutor(SimulationExecutor):
    def __init__(self, work_dir=None):
        """
        Initializes the LocalExecutor with a working directory.

        Args:
            work_dir (str, optional): The working directory inside the container. Defaults to the value of the DOCKER_WORK_DIR environment variable or '/app'.
        """
        
        if work_dir is None:
            work_dir = os.getenv("DOCKER_WORK_DIR", "/app")
        self.work_dir = work_dir

    def _get_container_name(self, method_config: Dict[str, Any]) -> str:
        """
        Constructs a unique container name based on the simulation method and simulation ID.

        Args:
            method_config (Dict[str, Any]): Configuration dictionary containing 'simulation_method' and 'simulation_id'.

        Returns:
            str: The generated container name.
        """

        simulation_method = method_config["simulation_method"]
        simulation_id = method_config["simulation_id"]
        return f"choras-{simulation_method}-simulation-{simulation_id}"

    def execute(self, method_config: Dict[str, Any], sim_config: Dict[str, Any]) -> tuple:
        """
        Executes a simulation by running a Docker container with the specified configuration.

        Args:
            method_config (Dict[str, Any]): Dictionary containing method-specific configuration, including 'container_image', 'simulation_method', and 'simulation_id'.
            sim_config (Dict[str, Any]): Dictionary containing simulation-specific configuration, including environment variables.

        Returns:
            tuple: The Docker container object representing the running simulation.

        Raises:
            Exception: If the Docker container fails to start.
        """

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
        """
        Cancels a running Docker container by its container name.

        Args:
            cancelation_info (Dict[str, Any]): Dictionary containing information to identify the container, typically including 'simulation_method' and 'simulation_id'.

        Raises:
            Exception: If the container cannot be killed or removed for reasons other than not being found.
        """

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