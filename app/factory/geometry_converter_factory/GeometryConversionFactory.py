from app.factory.geometry_converter_factory.DxfConversion import DxfConversion
from app.factory.geometry_converter_factory.GeometryConversionStrategy import GeometryConversionStrategy
from app.factory.geometry_converter_factory.ObjConversion import ObjConversion


class GeometryConversionFactory:
    @staticmethod
    def create_strategy(extension: str) -> GeometryConversionStrategy:
        # Remove the leading dot (if present) and convert to lowercase for consistency
        extension = extension.lstrip('.').lower()

        if extension == "obj":
            return ObjConversion()
        if extension == "dxf":
            return DxfConversion()
        else:
            raise ValueError(f"Unsupported format: {extension}")
