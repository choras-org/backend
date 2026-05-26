from abc import ABC, abstractmethod


class GeometryConversionStrategy(ABC):
    @abstractmethod
    def generate_3dm(self, obj_file_path, rhino_path):
        pass
