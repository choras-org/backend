from enum import Enum


class TaskType(Enum):
    GeometryCheck = "GeometryCheck"
    Mesh = "Mesh"
    SimulationMethod = "SimulationMethod"
    Generic = "Generic"
