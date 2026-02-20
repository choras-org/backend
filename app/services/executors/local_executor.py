import os
import uuid
import docker
import logging
from typing import Any, Dict
from .simulation_executor_interface import SimulationExecutor

logger = logging.getLogger(__name__)

class LocalExecutor(SimulationExecutor):
    def __init__(self, work_dir=None):
        if work_dir is None:
            work_dir = os.getenv("DOCKER_WORK_DIR", "/app")
        self.work_dir = work_dir
        self._jobs = {}  # job_id -> process

    def execute(self, method_config: Dict[str, Any], sim_config: Dict[str, Any]) -> str:
        """
        Spin up a Docker container locally using the image name and input variables.
        method_config: expects 'container_image' (str), optional 'command' (str or list)
        sim_config: json_file, optional 'env' (dict), 'volumes' (dict)
        Returns a job_id (str) for tracking.
        """
        
        image = method_config["container_image"] # update this to be taken from the discovery file
        env = sim_config.get("env", {})
        volumes = sim_config.get("volumes", {})
        job_id = str(uuid.uuid4())

        try:
            client = docker.from_env()
            container = client.containers.run(
                image=image,
                environment=env, # for file input, we can mount a volume and pass the path as an env variable
                volumes=volumes,
                detach=True,
                working_dir=self.work_dir,
                name=f"simjob_{job_id[:8]}",
                remove=True
            )
            self._jobs[job_id] = container
            return job_id, container
        
        except Exception as e:
            logger.error(f"Failed to start Docker container: {e}")
            raise