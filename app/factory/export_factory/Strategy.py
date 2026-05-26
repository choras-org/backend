import logging
from abc import ABC, abstractmethod

# Create logger for this module
logger = logging.getLogger(__name__)


class Strategy(ABC):
    @abstractmethod
    def export(self, export_type, params, simulationIds, zip_buffer):
        pass
