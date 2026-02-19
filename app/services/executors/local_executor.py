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
        #command = method_config.get("command")
        env = sim_config.get("env", {})
        volumes = sim_config.get("volumes", {})
        job_id = str(uuid.uuid4())

        #for the dynamic json file input file
        # sim_config = {
        #     "volumes": {
        #         "/host/path/input.json": {"bind": "/container/path/input.json", "mode": "ro"}
        #     },
        #     "env": {
        #         "INPUT_JSON": "/container/path/input.json"
        #     }
        # }
        print("Local Executor: Before running container...")

        try:
            client = docker.from_env()
            container = client.containers.run(
                image=image,
                environment=env,
                volumes=volumes,
                detach=True,
                working_dir=self.work_dir,
                name=f"simjob_{job_id[:8]}",
                remove=True
            )
            self._jobs[job_id] = container
            print(f"Local Executor: Container spinned up with {job_id}")
            return job_id, container
        
        # This code will only work to create a new container from inside another container if:

        # 1) The Docker socket is mounted into the running container:
        # The host’s Docker daemon must be accessible inside your container.
        # This is usually done by running your container with: -v /var/run/docker.sock:/var/run/docker.sock

        # 2) The container has the Docker SDK and (optionally) Docker CLI installed:
        # You already have the SDK (docker Python package), so that’s fine.

        # 3) The user inside the container has permission to access the Docker socket:
        # (Usually, running as root inside the container works, but for non-root, you may need to add the user to the docker group.)
        
        except Exception as e:
            logger.error(f"Failed to start Docker container: {e}")
            raise