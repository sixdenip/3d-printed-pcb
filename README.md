# 3D-printed PCB Toolchain

This MVP converts a KiCad-oriented DXF export into an OpenSCAD model and then an
STL: a rectangular base plate, raised trace centerlines, and cylindrical
through-holes. It deliberately produces **STL, not OBJ**.

## Setup

Python 3.10+ and OpenSCAD are required. Install the project and test tools:

```sh
python -m pip install -e '.[test]'
pytest
```

## DXF convention

The parser reads model-space `LINE`, `LWPOLYLINE`, and `POLYLINE` entities for
the outline and traces, and `CIRCLE` entities for holes. Coordinates are
treated as millimetres. By default it expects `Edge.Cuts`, `F.Cu`, and
`NPTH`/`Drill` layers. The outline is used to calculate the rectangular MVP
bounding box; traces are centerlines stroked at the configured width.

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
# Optional overrides: --base-thickness, --trace-height, --trace-width,
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