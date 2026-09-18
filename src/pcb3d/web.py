"""Minimal local Flask UI and JSON API; all geometry work remains in core modules."""

from pathlib import Path
import uuid

import yaml

from .config import LayerMapping, load_config, mapping_from_dict
from .models import GenerationParameters
from .pipeline import generate_from_board_file, parse_board_file
from .samples import get_sample, get_samples_catalog


def extract_board_geometry_dict(
    file_path: Path,
    mapping: LayerMapping,
    snap_tolerance: float,
    trace_width: float,
) -> dict:
    """Extract normalized 2D geometry for vector rendering from DXF or SVG."""
    geometry = parse_board_file(file_path, mapping)
    geometry = geometry.connect_traces_to_holes(snap_tolerance)

    raw_outlines = []
    if file_path.suffix.lower() == ".dxf":
        try:
            import ezdxf
            from .dxf import _iter_entities, _layer, _polyline
            doc = ezdxf.readfile(str(file_path))
            for entity in _iter_entities(doc):
                if mapping.accepts("outline", _layer(entity)) and entity.dxftype() in {"LINE", "LWPOLYLINE", "POLYLINE", "ARC"}:
                    try:
                        poly = _polyline(entity)
                        raw_outlines.append({
                            "points": [[p.x, p.y] for p in poly.points],
                            "closed": poly.closed
                        })
                    except Exception:
                        pass
        except Exception:
            pass

    min_x, min_y, max_x, max_y = geometry.bounds
    width, height = geometry.size

    return {
        "bounds": [min_x, min_y, max_x, max_y],
        "size": [width, height],
        "outlines": raw_outlines if raw_outlines else [{
            "points": [[p.x, p.y] for p in geometry.outline.points],
            "closed": geometry.outline.closed
        }],
        "traces": [
            {
                "points": [[p.x, p.y] for p in trace.points],
                "closed": trace.closed
            }
            for trace in geometry.traces
        ],
        "holes": [
            {
                "x": hole.center.x,
                "y": hole.center.y,
                "radius": hole.radius,
                "diameter": round(hole.radius * 2, 3),
            }
            for hole in geometry.holes
        ],
        "stats": {
            "trace_count": len(geometry.traces),
            "hole_count": len(geometry.holes),
            "width": round(width, 2),
            "height": round(height, 2),
            "trace_width": trace_width,
        }
    }


# Backward-compatible alias
extract_dxf_geometry_dict = extract_board_geometry_dict


def create_app(config_path: str | Path | None = None, *, output_dir: str | Path | None = None):
    try:
        from flask import Flask, Response, jsonify, render_template, request, send_from_directory
    except ImportError as exc:  # pragma: no cover - dependency is declared by the project
        raise RuntimeError("Flask is required for the web application") from exc

    app = Flask(__name__)
    app.config["PCB3D_MAPPING"] = load_config(config_path)
    directory = Path(output_dir or (Path.cwd() / "pcb3d-output"))
    directory.mkdir(parents=True, exist_ok=True)
    app.config["PCB3D_OUTPUT_DIR"] = directory

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.post("/api/generate")
    def generate():
        upload = request.files.get("dxf") or request.files.get("file")
        if upload is None or not upload.filename:
            return jsonify(error="A DXF file or SVG file is required"), 400
        ext = Path(upload.filename).suffix.lower()
        if ext not in (".dxf", ".svg"):
            return jsonify(error="Only DXF (.dxf) and SVG (.svg) files are supported"), 400
        try:
            mapping = app.config["PCB3D_MAPPING"]
            yaml_mapping = request.form.get("mapping")
            if yaml_mapping:
                mapping = mapping_from_dict(yaml.safe_load(yaml_mapping) or {})
            values = {
                key: request.form[key]
                for key in ("base_thickness", "trace_height", "trace_depth", "trace_width", "outline_margin", "snap_tolerance")
                if key in request.form and request.form[key] != ""
            }
            parameters = GenerationParameters.from_mapping(
                {**mapping.parameters.__dict__, **values}
            )
            # Filter NPTH mounting holes if explicitly disabled in form
            include_m4_raw = request.form.get("include_m4")
            if include_m4_raw is not None:
                include_m4 = include_m4_raw.lower() in ("1", "true", "on", "yes")
                if not include_m4:
                    mapping = LayerMapping(
                        outline=mapping.outline,
                        traces=mapping.traces,
                        holes=tuple(h for h in mapping.holes if h != "NPTH"),
                        parameters=parameters,
                    )
            job = uuid.uuid4().hex
            board_path = directory / f"{job}{ext}"
            output = directory / f"{job}.stl"
            upload.save(board_path)
            generate_from_board_file(
                board_path, output, mapping, parameters,
                openscad_executable=request.form.get("openscad", "openscad"),
            )
            board_geometry = extract_board_geometry_dict(
                board_path, mapping, parameters.snap_tolerance, parameters.trace_width
            )
            scad_name = output.with_suffix(".scad").name
            return jsonify(
                stl_url=f"/stl/{output.name}",
                scad_url=f"/scad/{scad_name}",
                job=job,
                dxf=board_geometry,
            )
        except (ValueError, OSError, RuntimeError, yaml.YAMLError) as exc:
            return jsonify(error=str(exc)), 400

    @app.post("/api/dxf-preview")
    def dxf_preview():
        upload = request.files.get("dxf") or request.files.get("file")
        if upload is None or not upload.filename:
            return jsonify(error="A DXF file or SVG file is required"), 400
        ext = Path(upload.filename).suffix.lower()
        if ext not in (".dxf", ".svg"):
            return jsonify(error="Only DXF (.dxf) and SVG (.svg) files are supported"), 400
        try:
            mapping = app.config["PCB3D_MAPPING"]
            yaml_mapping = request.form.get("mapping")
            if yaml_mapping:
                mapping = mapping_from_dict(yaml.safe_load(yaml_mapping) or {})

            snap_tolerance = float(request.form.get("snap_tolerance", mapping.parameters.snap_tolerance))
            trace_width = float(request.form.get("trace_width", mapping.parameters.trace_width))

            include_m4_raw = request.form.get("include_m4")
            if include_m4_raw is not None:
                include_m4 = include_m4_raw.lower() in ("1", "true", "on", "yes")
                if not include_m4:
                    mapping = LayerMapping(
                        outline=mapping.outline,
                        traces=mapping.traces,
                        holes=tuple(h for h in mapping.holes if h != "NPTH"),
                        parameters=mapping.parameters,
                    )

            temp_id = uuid.uuid4().hex
            temp_file = directory / f"preview_{temp_id}{ext}"
            upload.save(temp_file)

            try:
                geom_dict = extract_board_geometry_dict(
                    temp_file, mapping, snap_tolerance, trace_width
                )
            finally:
                temp_file.unlink(missing_ok=True)

            return jsonify(geom_dict)
        except Exception as exc:
            return jsonify(error=str(exc)), 400

    @app.get("/stl/<path:filename>")
    def stl(filename: str):
        return send_from_directory(directory, filename, mimetype="model/stl")

    @app.get("/scad/<path:filename>")
    def scad(filename: str):
        return send_from_directory(
            directory,
            filename,
            mimetype="application/x-openscad",
            as_attachment=True,
        )

    @app.get("/api/samples")
    def list_samples():
        return jsonify(get_samples_catalog())

    @app.get("/api/sample-dxf")
    def sample_dxf():
        include_m4 = request.args.get("m4_holes", "true").lower() in ("true", "1", "yes")
        sample_id = (
            request.args.get("id")
            or request.args.get("sample_id")
            or request.args.get("name")
        )
        sample = get_sample(sample_id)
        content = sample.generator(m4_holes=include_m4)
        filename = f"{sample.id}_with_m4.dxf" if include_m4 else f"{sample.id}_no_m4.dxf"
        return Response(
            content,
            mimetype="application/dxf",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

    return app
