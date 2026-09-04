"""Core library for turning a KiCad DXF export into an OpenSCAD/STL model."""

from .config import LayerMapping, load_config
from .dxf import parse_dxf
from .models import BoardGeometry, GenerationParameters
from .openscad import generate_openscad
from .pipeline import generate_from_dxf

__all__ = [
    "BoardGeometry",
    "GenerationParameters",
    "LayerMapping",
    "generate_openscad",
    "generate_from_dxf",
    "load_config",
    "parse_dxf",
]
