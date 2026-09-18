"""High-level, Flask-independent generation pipeline."""

from pathlib import Path

from .config import LayerMapping
from .dxf import parse_dxf
from .models import BoardGeometry, GenerationParameters, Hole, Point, Polyline
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


def generate_multilayer_stack(
    layers_info: list[dict],
    output_dir: str | Path,
    mapping: LayerMapping,
    base_parameters: GenerationParameters,
    *,
    openscad_executable: str = "openscad",
) -> list[dict]:
    """Compile a set of user-ordered stackable PCB layers with aligned coordinate frames.
    
    Each layer in layers_info contains:
      - 'path': Path to DXF or SVG
      - 'name': Layer display name
      - 'role': 'bottom', 'middle', 'top' (or auto-derived)
      - 'custom_params': optional parameter overrides
    """
    output_directory = Path(output_dir)
    output_directory.mkdir(parents=True, exist_ok=True)
    num_layers = len(layers_info)

    # 1. Parse all geometries
    parsed_layers = []
    for idx, info in enumerate(layers_info):
        geom = parse_board_file(info["path"], mapping)
        parsed_layers.append((info, geom))

    # 2. Compute unified bounding box to ensure concentric via alignment
    all_left = min(g.bounds[0] for _, g in parsed_layers)
    all_bottom = min(g.bounds[1] for _, g in parsed_layers)

    results = []
    for idx, (info, geom) in enumerate(parsed_layers):
        # Shift each layer to the shared stack origin so vias and mounting holes align perfectly
        move = lambda point: point.shifted(-all_left, -all_bottom)
        aligned_geom = BoardGeometry(
            outline=Polyline(tuple(move(p) for p in geom.outline.points), geom.outline.closed),
            traces=tuple(
                Polyline(tuple(move(p) for p in trace.points), trace.closed)
                for trace in geom.traces
            ),
            # Filter out M4 mounting holes (radius >= 2.0mm) for multi-layer stack
            holes=tuple(Hole(move(hole.center), hole.radius) for hole in geom.holes if hole.radius < 2.0),
        )

        # Resolve layer role from user's stack order if not explicitly forced
        role = info.get("role")
        if not role or role not in ("bottom", "middle", "top", "single"):
            if num_layers == 1:
                role = "single"
            elif idx == 0:
                role = "bottom"
            elif idx == num_layers - 1:
                role = "top"
            else:
                role = "middle"

        # Apply parameters with layer role and stack index
        layer_params = GenerationParameters.from_mapping({
            **base_parameters.__dict__,
            **info.get("custom_params", {}),
            "layer_role": role,
            "stack_index": idx,
        })

        source = generate_openscad(aligned_geom, layer_params)
        stem = Path(info["path"]).stem
        output_stl = output_directory / f"{stem}_L{idx + 1}_{role}.stl"
        run_openscad(source, output_stl, executable=openscad_executable)

        results.append({
            "index": idx,
            "name": info.get("name", f"Layer {idx + 1}"),
            "role": role,
            "stl_path": output_stl,
            "scad_path": output_stl.with_suffix(".scad"),
            "geometry": aligned_geom,
            "parameters": layer_params,
        })

    return results


# Backward-compatible alias
generate_from_dxf = generate_from_board_file

