import pytest


flask = pytest.importorskip("flask")

from pcb3d.web import create_app


def test_web_requires_dxf_upload(tmp_path):
    client = create_app(output_dir=tmp_path).test_client()
    response = client.post("/api/generate")
    assert response.status_code == 400
    assert "DXF file" in response.get_json()["error"]


def test_web_index_renders(tmp_path):
    client = create_app(output_dir=tmp_path).test_client()
    response = client.get("/")
    assert response.status_code == 200
    assert b"PCB3D Studio" in response.data


def test_web_sample_dxf_endpoint(tmp_path):
    client = create_app(output_dir=tmp_path).test_client()
    response = client.get("/api/sample-dxf")
    assert response.status_code == 200
    assert response.mimetype == "application/dxf"
    assert b"Edge.Cuts" in response.data
    assert b"F.Cu" in response.data
    assert b"NPTH" in response.data


def test_web_sample_dxf_optional_m4(tmp_path):
    client = create_app(output_dir=tmp_path).test_client()
    response_no_m4 = client.get("/api/sample-dxf?m4_holes=0")
    assert response_no_m4.status_code == 200
    assert b"Edge.Cuts" in response_no_m4.data
    assert b"F.Cu" in response_no_m4.data
    assert b"NPTH" not in response_no_m4.data
    assert b"Drill" in response_no_m4.data


def test_web_samples_catalog_endpoint(tmp_path):
    client = create_app(output_dir=tmp_path).test_client()
    response = client.get("/api/samples")
    assert response.status_code == 200
    data = response.get_json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert data[0]["id"] == "sample_pcb"
    assert "DIP-8" in data[0]["name"]


def test_web_sample_dxf_by_id(tmp_path):
    client = create_app(output_dir=tmp_path).test_client()
    response = client.get("/api/sample-dxf?id=sample_pcb")
    assert response.status_code == 200
    assert response.mimetype == "application/dxf"
    assert b"Edge.Cuts" in response.data


def test_web_generate_excludes_m4_when_include_m4_false(tmp_path):
    import io
    import shutil
    from pcb3d.samples import generate_dip8_sample_dxf
    if not shutil.which("openscad"):
        pytest.skip("OpenSCAD executable not available on PATH")

    client = create_app(output_dir=tmp_path).test_client()
    # DXF has M4 holes included
    dxf_data = generate_dip8_sample_dxf(m4_holes=True).encode("utf-8")
    data = {
        "dxf": (io.BytesIO(dxf_data), "sample_with_m4.dxf"),
        "include_m4": "0",
    }
    response = client.post("/api/generate", data=data, content_type="multipart/form-data")
    assert response.status_code == 200
    job = response.get_json()["job"]
    scad_file = tmp_path / f"{job}.scad"
    assert scad_file.is_file()
    scad_content = scad_file.read_text()
    # M4 holes have radius 2.2mm; they should be completely omitted from the SCAD difference
    assert "r=2.20000" not in scad_content
    # Component holes (radius 0.5mm) should remain
    assert "r=0.50000" in scad_content
    # Generated response also includes 2D dxf geometry
    assert "dxf" in response.get_json()
    assert response.get_json()["dxf"]["stats"]["hole_count"] == 12


def test_web_dxf_preview_requires_file(tmp_path):
    client = create_app(output_dir=tmp_path).test_client()
    response = client.post("/api/dxf-preview")
    assert response.status_code == 400
    assert "DXF file" in response.get_json()["error"]


def test_web_dxf_preview_success(tmp_path):
    import io
    from pcb3d.samples import generate_dip8_sample_dxf
    client = create_app(output_dir=tmp_path).test_client()
    dxf_data = generate_dip8_sample_dxf(m4_holes=True).encode("utf-8")
    data = {
        "dxf": (io.BytesIO(dxf_data), "sample_with_m4.dxf"),
        "include_m4": "1",
    }
    response = client.post("/api/dxf-preview", data=data, content_type="multipart/form-data")
    assert response.status_code == 200
    payload = response.get_json()
    assert "bounds" in payload
    assert "size" in payload
    assert payload["size"] == [44.0, 28.0]
    assert len(payload["outlines"]) >= 1
    assert len(payload["traces"]) >= 1
    # 4 M4 mounting holes + 4 connector pad holes + 8 DIP-8 pin holes = 16 holes
    assert len(payload["holes"]) == 16
    assert payload["stats"]["hole_count"] == 16
    assert payload["stats"]["trace_count"] >= 1


def test_web_dxf_preview_excludes_m4_when_disabled(tmp_path):
    import io
    from pcb3d.samples import generate_dip8_sample_dxf
    client = create_app(output_dir=tmp_path).test_client()
    dxf_data = generate_dip8_sample_dxf(m4_holes=True).encode("utf-8")
    data = {
        "dxf": (io.BytesIO(dxf_data), "sample_with_m4.dxf"),
        "include_m4": "0",
    }
    response = client.post("/api/dxf-preview", data=data, content_type="multipart/form-data")
    assert response.status_code == 200
    payload = response.get_json()
    # NPTH filtered out: 4 connector pad holes + 8 DIP-8 pin holes = 12 holes remain
    assert len(payload["holes"]) == 12
    assert payload["stats"]["hole_count"] == 12
    # No hole should have radius 2.2 (M4)
    radii = [h["radius"] for h in payload["holes"]]
    assert 2.2 not in radii


def test_web_generate_returns_scad_url_and_serves_scad(tmp_path):
    import io
    import shutil
    from pcb3d.samples import generate_dip8_sample_dxf
    if not shutil.which("openscad"):
        pytest.skip("OpenSCAD executable not available on PATH")

    client = create_app(output_dir=tmp_path).test_client()
    dxf_data = generate_dip8_sample_dxf(m4_holes=True).encode("utf-8")
    data = {
        "dxf": (io.BytesIO(dxf_data), "sample_with_m4.dxf"),
    }
    response = client.post("/api/generate", data=data, content_type="multipart/form-data")
    assert response.status_code == 200
    payload = response.get_json()
    assert "scad_url" in payload
    assert "stl_url" in payload
    assert payload["scad_url"].startswith("/scad/")
    assert payload["scad_url"].endswith(".scad")

    # Fetch SCAD file from web endpoint
    scad_response = client.get(payload["scad_url"])
    assert scad_response.status_code == 200
    assert "application/x-openscad" in scad_response.mimetype
    assert "attachment" in scad_response.headers.get("Content-Disposition", "")
    assert b"difference()" in scad_response.data
    assert b"cylinder" in scad_response.data


def test_web_scad_endpoint_404_on_missing_file(tmp_path):
    client = create_app(output_dir=tmp_path).test_client()
    response = client.get("/scad/nonexistent.scad")
    assert response.status_code == 404


def test_web_generate_svg_file(tmp_path):
    import io
    import shutil
    if not shutil.which("openscad"):
        pytest.skip("OpenSCAD executable not available on PATH")

    client = create_app(output_dir=tmp_path).test_client()
    svg_data = b"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="40mm" height="25mm" viewBox="0 0 40 25">
  <g id="Edge.Cuts">
    <rect x="0" y="0" width="40" height="25" />
  </g>
  <g id="F.Cu">
    <path d="M 5 5 L 20 5" />
  </g>
  <g id="Drill">
    <circle cx="20" cy="5" r="1.0" />
  </g>
</svg>"""
    data = {
        "dxf": (io.BytesIO(svg_data), "board.svg"),
    }
    response = client.post("/api/generate", data=data, content_type="multipart/form-data")
    assert response.status_code == 200
    payload = response.get_json()
    assert "stl_url" in payload
    assert "scad_url" in payload
    assert "dxf" in payload
    assert payload["dxf"]["size"] == [40.0, 25.0]
    assert payload["dxf"]["stats"]["hole_count"] == 1
    assert payload["dxf"]["stats"]["trace_count"] == 1


def test_web_preview_svg_file(tmp_path):
    import io
    client = create_app(output_dir=tmp_path).test_client()
    svg_data = b"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="50mm" height="30mm" viewBox="0 0 50 30">
  <g id="Edge.Cuts">
    <path d="M 0 0 L 50 0 L 50 30 L 0 30 Z" />
  </g>
  <g id="F.Cu">
    <path d="M 5 5 L 20 5 L 20 15" />
    <path d="M 30 15 L 45 15" />
  </g>
  <g id="Drill">
    <circle cx="20" cy="15" r="1.0" />
  </g>
</svg>"""
    data = {
        "dxf": (io.BytesIO(svg_data), "board.svg"),
    }
    response = client.post("/api/dxf-preview", data=data, content_type="multipart/form-data")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["size"] == [50.0, 30.0]
    assert payload["stats"]["trace_count"] == 2
    assert payload["stats"]["hole_count"] == 1


def test_web_rejects_unsupported_file_extension(tmp_path):
    import io
    client = create_app(output_dir=tmp_path).test_client()
    data = {
        "dxf": (io.BytesIO(b"fake data"), "board.pdf"),
    }
    response = client.post("/api/generate", data=data, content_type="multipart/form-data")
    assert response.status_code == 400
    assert "Only DXF (.dxf) and SVG (.svg) files are supported" in response.get_json()["error"]


def test_web_generate_stack_endpoint(tmp_path):
    import io
    import shutil
    from pcb3d.samples import generate_dip8_sample_dxf, generate_dip8_shield_sample_dxf
    if not shutil.which("openscad"):
        pytest.skip("OpenSCAD executable not available on PATH")

    client = create_app(output_dir=tmp_path).test_client()
    dxf1 = generate_dip8_sample_dxf(m4_holes=True).encode("utf-8")
    dxf2 = generate_dip8_shield_sample_dxf(m4_holes=True).encode("utf-8")

    data = {
        "layers": [
            (io.BytesIO(dxf1), "layer1_base.dxf"),
            (io.BytesIO(dxf2), "layer2_shield.dxf"),
        ],
        "roles": ["bottom", "top"],
        "names": ["Base Board", "Top Shield"],
        "stacking_pins": "1",
        "stacking_pin_diameter": "3.0",
        "stacking_pin_height": "1.2",
    }
    response = client.post("/api/generate-stack", data=data, content_type="multipart/form-data")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["total_layers"] == 2
    assert len(payload["layers"]) == 2
    assert payload["layers"][0]["role"] == "bottom"
    assert payload["layers"][1]["role"] == "top"
    assert "stl_url" in payload["layers"][0]
    assert "scad_url" in payload["layers"][0]

    # Verify 2D vector circuit payload is fully populated for both layers
    for layer in payload["layers"]:
        assert "dxf" in layer
        assert "base_thickness" in layer
        assert "trace_depth" in layer
        dxf_info = layer["dxf"]
        assert "bounds" in dxf_info
        assert isinstance(dxf_info["bounds"], list)
        assert len(dxf_info["bounds"]) == 4
        assert "size" in dxf_info
        assert len(dxf_info["size"]) == 2
        assert "outlines" in dxf_info
        assert len(dxf_info["outlines"]) >= 1
        assert "traces" in dxf_info
        assert "holes" in dxf_info
        assert "stats" in dxf_info
        assert "trace_count" in dxf_info["stats"]
        assert "hole_count" in dxf_info["stats"]
        # Verify M4 mounting holes (radius >= 2.0mm) are disabled in multi-layer stack
        for hole in dxf_info["holes"]:
            assert hole["radius"] < 2.0

    # Verify Stack ZIP bundle endpoints
    import zipfile
    job = payload["job"]

    # Download STLs as ZIP
    res_stl_zip = client.get(f"/api/stack-zip/{job}/stl")
    assert res_stl_zip.status_code == 200
    assert res_stl_zip.mimetype == "application/zip"
    with zipfile.ZipFile(io.BytesIO(res_stl_zip.data)) as zf:
        namelist = zf.namelist()
        assert len(namelist) == 2
        assert all(n.endswith(".stl") for n in namelist)

    # Download SCADs as ZIP
    res_scad_zip = client.get(f"/api/stack-zip/{job}/scad")
    assert res_scad_zip.status_code == 200
    assert res_scad_zip.mimetype == "application/zip"
    with zipfile.ZipFile(io.BytesIO(res_scad_zip.data)) as zf:
        namelist = zf.namelist()
        assert len(namelist) == 2
        assert all(n.endswith(".scad") for n in namelist)

    # Invalid file type
    res_invalid = client.get(f"/api/stack-zip/{job}/pdf")
    assert res_invalid.status_code == 400

    # Non-existent job
    res_missing = client.get("/api/stack-zip/nonexistentjob123/stl")
    assert res_missing.status_code == 404

