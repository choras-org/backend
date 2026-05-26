import io
from typing import List

from app.factory.export_factory.ExportAuralization import ExportAuralization
from app.factory.export_factory.ExportEdc import ExportEdc
from app.factory.export_factory.ExportExcel import ExportExcel
from app.factory.export_factory.ExportParameters import ExportParameters


class Factory:
    strategies = {
        "xlsx": ExportExcel(),
        "Parameters": ExportParameters(),
        "EDC": ExportEdc(),
        "Auralization": ExportAuralization(),
    }

    @staticmethod
    def get_exporter(export_type: str, params: List, simulationId: List, zip_buffer: io.BytesIO) -> io.BytesIO:
        strategy = Factory.strategies.get(export_type, None)
        return strategy.export(export_type, params, simulationId, zip_buffer)
