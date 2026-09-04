"""High-level, Flask-independent generation pipeline."""

from pathlib import Path

from .config import LayerMapping
from .dxf import parse_dxf
from .models import GenerationParameters
from .openscad import generate_openscad, run_openscad


def generate_from_dxf(
    dxf_path: str | Path,
    output_stl: str | Path,
    mapping: LayerMapping,
    parameters: GenerationParameters | None = None,
    *,
    openscad_executable: str = "openscad",
) -> Path:
    geometry = parse_dxf(dxf_path, mapping)
    source = generate_openscad(geometry, parameters or mapping.parameters)
    return run_openscad(source, output_stl, executable=openscad_executable)
