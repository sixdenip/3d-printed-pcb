"""Minimal local Flask UI and JSON API; all geometry work remains in core modules."""

from pathlib import Path
import uuid

import yaml

from .config import load_config, mapping_from_dict
from .models import GenerationParameters
from .pipeline import generate_from_dxf
from .samples import get_sample, get_samples_catalog


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
        upload = request.files.get("dxf")
        if upload is None or not upload.filename:
            return jsonify(error="A DXF file is required"), 400
        try:
            mapping = app.config["PCB3D_MAPPING"]
            yaml_mapping = request.form.get("mapping")
            if yaml_mapping:
                mapping = mapping_from_dict(yaml.safe_load(yaml_mapping) or {})
            values = {
                key: request.form[key]
                for key in ("base_thickness", "trace_height", "trace_width", "outline_margin")
                if key in request.form and request.form[key] != ""
            }
            parameters = GenerationParameters.from_mapping(
                {**mapping.parameters.__dict__, **values}
            )
            job = uuid.uuid4().hex
            dxf_path = directory / f"{job}.dxf"
            output = directory / f"{job}.stl"
            upload.save(dxf_path)
            generate_from_dxf(
                dxf_path, output, mapping, parameters,
                openscad_executable=request.form.get("openscad", "openscad"),
            )
            return jsonify(stl_url=f"/stl/{output.name}", job=job)
        except (ValueError, OSError, RuntimeError, yaml.YAMLError) as exc:
            return jsonify(error=str(exc)), 400

    @app.get("/stl/<path:filename>")
    def stl(filename: str):
        return send_from_directory(directory, filename, mimetype="model/stl")

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
