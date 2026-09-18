"""High-level, Flask-independent generation pipeline."""

from pathlib import Path

from .config import LayerMapping
from .dxf import parse_dxf
from .models import BoardGeometry, GenerationParameters
from .openscad import generate_openscad, run_openscad
from .svg import parse_svg


def parse_board_file(source: str | Path, mapping: LayerMapping) -> BoardGeometry:
    """Parse either a DXF or SVG board file based on extension."""
    path = Path(source)
    if path.suffix.lower() == ".svg":
        return parse_svg(path, mapping)
    return parse_dxf(path, mapping)


def generate_from_board_file(
    board_path: str | Path,
    output_stl: str | Path,
    mapping: LayerMapping,
    parameters: GenerationParameters | None = None,
    *,
    openscad_executable: str = "openscad",
) -> Path:
    """End-to-end pipeline: load DXF or SVG, build CSG, and compile STL."""
    geometry = parse_board_file(board_path, mapping)
    source = generate_openscad(geometry, parameters or mapping.parameters)
    return run_openscad(source, output_stl, executable=openscad_executable)


# Backward-compatible alias
generate_from_dxf = generate_from_board_file
