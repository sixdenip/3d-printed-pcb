"""Command line interface driven by the same YAML config as the web app."""

import argparse
import sys
from pathlib import Path

from .config import load_config
from .models import GenerationParameters
from .pipeline import generate_from_dxf


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pcb3d", description="Generate an STL from a KiCad DXF")
    subparsers = parser.add_subparsers(dest="command", required=True)
    generate = subparsers.add_parser("generate", help="parse DXF and run OpenSCAD")
    generate.add_argument("--dxf", required=True, type=Path)
    generate.add_argument("--output", required=True, type=Path)
    generate.add_argument("--config", type=Path, help="YAML layer mapping and parameter defaults")
    generate.add_argument("--openscad", default="openscad", help="OpenSCAD executable")
    generate.add_argument("--base-thickness", type=float)
    generate.add_argument("--trace-height", type=float)
    generate.add_argument("--trace-width", type=float)
    generate.add_argument("--outline-margin", type=float)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command != "generate":
        return 2
    try:
        mapping = load_config(args.config)
        overrides = {
            key: value for key, value in {
                "base_thickness": args.base_thickness,
                "trace_height": args.trace_height,
                "trace_width": args.trace_width,
                "outline_margin": args.outline_margin,
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
