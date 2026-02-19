from abc import ABC, abstractmethod
from typing import Any, Dict

class SimulationExecutor(ABC):
    @abstractmethod
    def execute(self, method_config: Dict[str, Any], sim_config: Dict[str, Any]):  #-> str
        """Start the simulation job and return a job ID or handle."""
        pass

    # @abstractmethod
    # def get_status(self, job_id: str) -> str:
    #     """Get the status of a running job by its ID."""
    #     pass

    # @abstractmethod
    # def cancel(self, job_id: str) -> bool:
    #     """Cancel a running job by its ID."""
    #     pass