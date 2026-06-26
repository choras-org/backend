from enum import Enum


class GeometryProcessingStatus(Enum):
    Pending = "Pending"        # queued, not started
    Processing = "Processing"  # inspect/repair running
    Completed = "Completed"    # finished successfully
    Failed = "Failed"          # pipeline raised
