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



