"""Command line interface driven by the same YAML config as the web app."""

import argparse
import sys
from pathlib import Path

from .config import LayerMapping, load_config
from .models import GenerationParameters
from .pipeline import generate_from_dxf


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pcb3d", description="Generate an STL from a KiCad DXF or SVG export")
    subparsers = parser.add_subparsers(dest="command", required=True)
    generate = subparsers.add_parser("generate", help="parse DXF or SVG and run OpenSCAD")
    generate.add_argument("--dxf", "--input", "-i", dest="dxf", required=True, type=Path, help="Input DXF or SVG file")
    generate.add_argument("--output", "-o", required=True, type=Path, help="Output STL path")
    generate.add_argument("--config", type=Path, help="YAML layer mapping and parameter defaults")
    generate.add_argument("--openscad", default="openscad", help="OpenSCAD executable")
    generate.add_argument("--base-thickness", type=float)
    generate.add_argument("--trace-height", type=float, help="Trench depth (legacy flag)")
    generate.add_argument("--trace-depth", type=float, help="Trench depth below substrate surface")
    generate.add_argument("--trace-width", type=float)
    generate.add_argument("--outline-margin", type=float)
    generate.add_argument("--snap-tolerance", type=float, help="Max distance to snap trace endpoints to holes")
    generate.add_argument(
        "--include-m4",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Include NPTH/M4 mounting holes (default: determined by config)",
    )
    generate.add_argument(
        "--stacking-pins",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Include corner alignment stacking pegs and socket recesses for multi-layer stacking",
    )
    generate.add_argument("--stacking-pin-diameter", type=float, default=3.0, help="Corner stacking pin diameter in mm")
    generate.add_argument("--stacking-pin-height", type=float, default=1.2, help="Corner stacking pin height in mm")
    generate.add_argument("--stacking-clearance", type=float, default=0.15, help="Radial clearance fit for sockets in mm")
    generate.add_argument("--layer-role", choices=["bottom", "middle", "top", "single"], default="single", help="Stacking role of this layer")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command != "generate":
        return 2
    try:
        mapping = load_config(args.config)
        if args.include_m4 is False:
            mapping = LayerMapping(
                outline=mapping.outline,
                traces=mapping.traces,
                holes=tuple(h for h in mapping.holes if h != "NPTH"),
                parameters=mapping.parameters,
            )
        trace_val = args.trace_depth if args.trace_depth is not None else args.trace_height
        overrides = {
            key: value for key, value in {
                "base_thickness": args.base_thickness,
                "trace_height": trace_val,
                "trace_width": args.trace_width,
                "outline_margin": args.outline_margin,
                "snap_tolerance": args.snap_tolerance,
                "stacking_pins": args.stacking_pins,
                "stacking_pin_diameter": args.stacking_pin_diameter,
                "stacking_pin_height": args.stacking_pin_height,
                "stacking_clearance": args.stacking_clearance,
                "layer_role": args.layer_role,
            }.items() if value is not None
        }
        parameters = GenerationParameters.from_mapping(
            {**mapping.parameters.__dict__, **overrides}
        )
        output = generate_from_dxf(
            args.dxf, args.output, mapping, parameters, openscad_executable=args.openscad
        )

        print(output)
        return 0
    except (ValueError, OSError, RuntimeError) as exc:
        print(f"pcb3d: error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
