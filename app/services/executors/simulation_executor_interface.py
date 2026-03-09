from abc import ABC, abstractmethod
from typing import Any, Dict

class SimulationExecutor(ABC):
    @abstractmethod
    def execute(self, method_config: Dict[str, Any], sim_config: Dict[str, Any]):  #-> str
        """Start the simulation job and return a job ID & container."""
        pass

    @abstractmethod
    def cancel(self, simulation_id: int) -> dict:
        """Cancel a running job by its ID."""
        pass