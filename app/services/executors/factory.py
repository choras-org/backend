from app.types import ResourceType
from app.services.executors.local_executor import LocalExecutor
from app.services.executors.cloud_executor import CloudExecutor
from app.services.executors.simulation_executor_interface import SimulationExecutor
from config import CloudConfig


def executor_factory(resource_type: ResourceType, 
                     entry_file: str = None) -> SimulationExecutor: 
    """
    Factory function to create a SimulationExecutor based on the resource type.

    Args:
        resource_type (ResourceType): The type of resource to use (LOCAL or CLOUD).
        entry_file (str, optional): The entry file for the executor, used for cloud execution. Defaults to None.

    Returns:
        SimulationExecutor: An instance of LocalExecutor or CloudExecutor depending on the resource type.

    Raises:
        ValueError: If the resource type is not supported.
    """
    
    if resource_type == ResourceType.LOCAL:
        return LocalExecutor()
    elif resource_type == ResourceType.CLOUD:
        return CloudExecutor(
            CloudConfig.CLOUD_EXECUTOR_HOST,
            CloudConfig.CLOUD_EXECUTOR_USER,
            key_path = CloudConfig.CLOUD_EXECUTOR_KEY_PATH,
            remote_work_dir=CloudConfig.CLOUD_EXECUTOR_DIRECTORY,
            entry_file = entry_file
        ) 
    else:
        raise ValueError(f"Unsupported resource type: {resource_type}")

