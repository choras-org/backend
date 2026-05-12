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
    Resolves the host path corresponding to a given container path by inspecting
    the current container's mounts using the Docker socket.

    Args:
        container_path (str): The absolute path inside the container to resolve.

    Returns:
        str: The corresponding absolute path on the host machine.

    Raises:
        RuntimeError: If no mount is found covering the given container path.
        Exception: If there is an error communicating with Docker or resolving the path.
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

        # Common kwargs shared by the GPU-on and GPU-off run() calls.
        _run_kwargs = dict(
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
            remove=True,
        )

        try:
            client = docker.from_env()
            # Try to pass the host GPU through to the spawned method container.
            # `count=-1` means "all visible GPUs". This succeeds on Linux + Windows
            # hosts that have nvidia-container-toolkit / a CUDA driver installed.
            # On macOS, on Linux hosts without the nvidia runtime, and on any
            # other host with no GPU, the Docker daemon rejects the request with
            # a 500 "could not select device driver '' with capabilities: [[gpu]]".
            # We catch that specific failure and transparently retry without the
            # device request -- so CPU-only methods (pyroomacoustics, DE on a
            # laptop without an NVIDIA GPU, etc.) keep working unchanged.
            try:
                container = client.containers.run(
                    **_run_kwargs,
                    device_requests=[
                        docker.types.DeviceRequest(count=-1, capabilities=[["gpu"]])
                    ],
                )
                logger.info(f"Container {container_name} started with GPU passthrough")
                return container
            except docker.errors.APIError as gpu_err:
                # APIError covers the 500 from the daemon. Only fall back if
                # the failure is specifically about the [[gpu]] capability;
                # any other 500 (port conflict, OOM, etc.) is a real error
                # and should propagate.
                msg = str(gpu_err)
                if "[[gpu]]" not in msg and "could not select device driver" not in msg:
                    raise
                logger.warning(
                    f"GPU passthrough rejected by Docker daemon "
                    f"({type(gpu_err).__name__}: {msg.splitlines()[0]}). "
                    f"Retrying CPU-only for image {image}."
                )
                # Defensive: clean up any half-created container with the same name.
                try:
                    client.containers.get(container_name).remove(force=True)
                except Exception:
                    pass
                container = client.containers.run(**_run_kwargs)
                logger.info(f"Container {container_name} started CPU-only")
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