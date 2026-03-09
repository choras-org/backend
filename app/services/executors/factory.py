from app.types import ResourceType
from app.services.executors.local_executor import LocalExecutor
from app.services.executors.cloud_executor import CloudExecutor
from app.services.executors.simulation_executor_interface import SimulationExecutor
from config import CloudConfig


def executor_factory(resource_type: ResourceType, 
                     entry_file: str = None) -> SimulationExecutor: 
    
    if resource_type == ResourceType.LOCAL:
        return LocalExecutor()
    else:
        return CloudExecutor(
        CloudConfig.CLOUD_EXECUTOR_HOST,
        CloudConfig.CLOUD_EXECUTOR_USER,
        key_path = CloudConfig.CLOUD_EXECUTOR_KEY_PATH,
        remote_work_dir=CloudConfig.CLOUD_EXECUTOR_DIRECTORY,
        entry_file = entry_file
    )
