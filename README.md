# 3D-printed PCB Toolchain

This MVP converts KiCad DXF or SVG exports into an OpenSCAD model and then an
STL: a rectangular dielectric base plate, subtractive recessed trace trenches (channels
carved lower than the base surface), and cylindrical through-holes. It deliberately produces **STL, not OBJ**.

For full architectural details, data flow, and development guidelines, see [AGENT_GUIDE.md](AGENT_GUIDE.md).

## Setup

Python 3.10+ and OpenSCAD are required. Install the project and test tools:

```sh
python -m pip install -e '.[test]'
pytest
```

## DXF and SVG conventions

The parser accepts both **AutoCAD DXF** (`.dxf`) and **Scalable Vector Graphics** (`.svg`, e.g. as exported by KiCad).

- **DXF**: Reads model-space `LINE`, `LWPOLYLINE`, `POLYLINE`, and `ARC` entities for outline and traces, and `CIRCLE` entities for holes.
- **SVG**: Reads `<path>`, `<rect>`, `<line>`, `<polyline>`, `<polygon>` for outline and traces, and `<circle>` or circular hole paths for through-holes, with layer classification via `<g id="...">` or classes. Coordinates and units (`mm`, `in`, `cm`, `pt`, `px`) are automatically normalized to millimetres.

By default, layers `Edge.Cuts` (outline), `F.Cu` (traces), and `NPTH`/`Drill` (holes) are recognized. Traces are centerlines stroked at the configured width.

## Configuration

Layer names and dimensions are YAML-driven:

```yaml
layers:
  outline: Board          # string or list
  traces: [CopperTop, CopperBottom]
  holes: Drill
parameters:
  base_thickness: 1.6
  trace_height: 0.4
  trace_width: 0.4
  outline_margin: 0
```

## CLI

```sh
pcb3d generate --dxf board.dxf --output board.stl --config pcb3d.yml
# Optional overrides: --base-thickness, --trace-depth (or --trace-height), --trace-width,
# --outline-margin, and --openscad /path/to/openscad
```

## Local web app

```sh
flask --app 'pcb3d.web:create_app()' run --debug
```

Open <http://127.0.0.1:5000/> to upload a DXF and edit dimensions. The
`POST /api/generate` endpoint accepts a multipart `dxf` file plus parameter
fields and returns an STL URL. `GET /stl/<filename>` serves generated files.
The page includes a small Three.js CDN preview of the resulting STL.