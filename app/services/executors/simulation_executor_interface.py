from abc import ABC, abstractmethod
from typing import Any, Dict

class SimulationExecutor(ABC):
    @abstractmethod
    def execute(self, method_config: Dict[str, Any], sim_config: Dict[str, Any]):  #-> str
        """
        Starts the simulation job and returns a job ID and container.

        Args:
            method_config (Dict[str, Any]): Configuration for the simulation method.
            sim_config (Dict[str, Any]): Configuration for the simulation run.

        Returns:
            Any: Job ID and container information for the started simulation.
        """
        pass

    @abstractmethod
    def cancel(self, cancelation_info: Dict[str, Any]):
        """
        Cancels a running job by its ID.

        Args:
            cancelation_info (Dict[str, Any]): Information required to cancel the job (e.g., job ID).

        Returns:
            None
        """
        pass