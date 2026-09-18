"""Core library for turning a KiCad DXF export into an OpenSCAD/STL model."""

from .config import LayerMapping, load_config
from .dxf import DxfParseError, parse_dxf
from .models import BoardGeometry, GenerationParameters
from .openscad import generate_openscad
from .pipeline import generate_from_board_file, generate_from_dxf, parse_board_file
from .svg import SvgParseError, parse_svg

__all__ = [
    "BoardGeometry",
    "DxfParseError",
    "GenerationParameters",
    "LayerMapping",
    "SvgParseError",
    "generate_from_board_file",
    "generate_from_dxf",
    "generate_openscad",
    "load_config",
    "parse_board_file",
    "parse_dxf",
    "parse_svg",
]
