from enum import Enum


class Status(Enum):
    Uncreated = "Uncreated"
    Created = "Created"
    Queued = "Queued"
    InProgress = "InProgress"
    ProcessingResults = "ProcessingResults"
    Completed = "Completed"
    Cancelled = "Cancelled"
    Error = "Error"
