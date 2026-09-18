from pathlib import Path

import ezdxf
import pytest

from pcb3d.config import mapping_from_dict
from pcb3d.dxf import parse_dxf
from pcb3d.models import BoardGeometry, GenerationParameters, Hole, Point, Polyline
from pcb3d.openscad import generate_openscad


def simple_geometry() -> BoardGeometry:
    return BoardGeometry(
        Polyline((Point(10, 20), Point(30, 20), Point(30, 40), Point(10, 40)), True),
        (Polyline((Point(12, 22), Point(28, 22))),),
        (Hole(Point(15, 25), 1.0),),
    )


def test_parameters_validate_and_reject_unknown_values():
    assert GenerationParameters.from_mapping({"trace_height": 0.5}).trace_height == 0.5
    assert GenerationParameters.from_mapping({"trace_depth": 0.5}).trace_depth == 0.5
    assert GenerationParameters.from_mapping({"trace_depth": 0.5}).trace_height == 0.5
    with pytest.raises(ValueError):
        GenerationParameters.from_mapping({"trace_width": 0})
    with pytest.raises(ValueError):
        GenerationParameters.from_mapping({"not_a_parameter": 1})
    with pytest.raises(ValueError, match="less than base_thickness"):
        GenerationParameters(base_thickness=1.6, trace_height=1.6).validate()
    with pytest.raises(ValueError, match="less than base_thickness"):
        GenerationParameters(base_thickness=1.6, trace_height=2.0).validate()


def test_config_accepts_strings_and_lists():
    mapping = mapping_from_dict({
        "layers": {"outline": "Board", "traces": ["CopperTop", "CopperBottom"], "holes": "Drill"},
        "parameters": {"base_thickness": 2},
    })
    assert mapping.outline == ("Board",)
    assert mapping.traces == ("CopperTop", "CopperBottom")
    assert mapping.parameters.base_thickness == 2


def test_openscad_source_contains_base_trenches_and_through_hole():
    params = GenerationParameters(base_thickness=1.6, trace_height=0.4)
    source = generate_openscad(simple_geometry(), params)
    assert "cube([20.00000, 20.00000, base_thickness])" in source
    assert "linear_extrude" in source
    # Trench should cut from base_thickness - trace_height (1.6 - 0.4 = 1.2)
    assert "translate([0, 0, 1.20000])" in source
    # Trench cut extends 0.1mm above surface to ensure clean CSG difference
    assert "linear_extrude(height=0.50000)" in source
    assert "cylinder(h=base_thickness + 0.2" in source
    assert "difference()" in source
    assert "trace trench with 2 points" in source



def test_parse_dxf_by_configured_layers(tmp_path: Path):
    doc = ezdxf.new("R2010")
    model = doc.modelspace()
    model.add_lwpolyline([(0, 0), (10, 0), (10, 8), (0, 8)], close=True, dxfattribs={"layer": "Board"})
    model.add_line((1, 1), (9, 1), dxfattribs={"layer": "Copper"})
    model.add_circle((3, 3), radius=0.8, dxfattribs={"layer": "Drill"})
    path = tmp_path / "board.dxf"
    doc.saveas(path)
    geometry = parse_dxf(path, mapping_from_dict({
        "layers": {"outline": "Board", "traces": "Copper", "holes": "Drill"}
    }))
    assert geometry.size == (10, 8)
    assert len(geometry.traces) == 1
    assert geometry.holes[0].radius == 0.8


def test_run_openscad_generates_valid_stl(tmp_path: Path):
    import shutil
    from pcb3d.openscad import run_openscad
    if not shutil.which("openscad"):
        pytest.skip("OpenSCAD executable not available on PATH")
    source = generate_openscad(simple_geometry(), GenerationParameters(base_thickness=1.6, trace_height=0.4))
    stl_path = tmp_path / "test_board.stl"
    result = run_openscad(source, stl_path)
    assert result.is_file()
    assert result.stat().st_size > 0


def test_connect_traces_to_holes_snaps_endpoints():
    # Hole at (10, 10) with radius 1.0. Trace starting at (11.3, 10.0) is 0.3mm outside hole.
    # With snap_tolerance 0.5, it should snap to (10, 10).
    geom = BoardGeometry(
        Polyline((Point(0, 0), Point(20, 0), Point(20, 20), Point(0, 20)), True),
        (Polyline((Point(11.3, 10.0), Point(18.0, 10.0))),),
        (Hole(Point(10.0, 10.0), 1.0),),
    )
    connected = geom.connect_traces_to_holes(snap_tolerance=0.5)
    assert connected.traces[0].points[0] == Point(10.0, 10.0)
    assert connected.traces[0].points[1] == Point(18.0, 10.0)


def test_sample_pcb_traces_connect_with_holes(tmp_path: Path):
    from pcb3d.samples import generate_dip8_sample_dxf
    from pcb3d.dxf import parse_dxf
    from pcb3d.config import LayerMapping
    from pcb3d.openscad import run_openscad
    import shutil

    dxf_content = generate_dip8_sample_dxf(m4_holes=True)
    dxf_path = tmp_path / "sample.dxf"
    dxf_path.write_text(dxf_content, encoding="utf-8")

    geom = parse_dxf(dxf_path, LayerMapping())
    # Verify all 7 traces have endpoints terminating directly at hole centers
    hole_centers = {hole.center for hole in geom.holes}
    for trace in geom.traces:
        assert trace.points[0] in hole_centers
        assert trace.points[-1] in hole_centers

    # Verify OpenSCAD compiles this connected geometry to STL without error
    if shutil.which("openscad"):
        source = generate_openscad(geom, GenerationParameters())
        stl_path = tmp_path / "sample.stl"
        out = run_openscad(source, stl_path)
        assert out.is_file()
        assert out.stat().st_size > 0


def test_cli_generate_no_include_m4(tmp_path: Path):
    from pcb3d.cli import main
    from pcb3d.samples import generate_dip8_sample_dxf
    import shutil

    if not shutil.which("openscad"):
        pytest.skip("OpenSCAD executable not available on PATH")

    dxf_path = tmp_path / "board_with_m4.dxf"
    dxf_path.write_text(generate_dip8_sample_dxf(m4_holes=True), encoding="utf-8")
    output_stl = tmp_path / "board_no_m4.stl"

    exit_code = main(["generate", "--dxf", str(dxf_path), "--output", str(output_stl), "--no-include-m4"])
    assert exit_code == 0
    assert output_stl.is_file()
    scad_content = output_stl.with_suffix(".scad").read_text()
    assert "r=2.20000" not in scad_content
    assert "r=0.50000" in scad_content


def test_parse_svg_with_layers(tmp_path: Path):
    from pcb3d.config import LayerMapping
    from pcb3d.svg import parse_svg

    svg_content = """<?xml version="1.0" encoding="UTF-8"?>
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
    <circle cx="30" cy="15" r="1.0" />
  </g>
  <g id="NPTH">
    <circle cx="5" cy="5" r="2.2" />
    <circle cx="45" cy="25" r="2.2" />
  </g>
</svg>"""
    svg_file = tmp_path / "kicad_sample.svg"
    svg_file.write_text(svg_content, encoding="utf-8")

    geom = parse_svg(svg_file, LayerMapping())
    assert geom.size == (50.0, 30.0)
    assert len(geom.traces) == 2
    assert len(geom.holes) == 4
    radii = {round(h.radius, 1) for h in geom.holes}
    assert 1.0 in radii
    assert 2.2 in radii


def test_parse_svg_shapes_and_arcs(tmp_path: Path):
    from pcb3d.config import LayerMapping
    from pcb3d.svg import parse_svg

    svg_content = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="40mm" height="40mm" viewBox="0 0 40 40">
  <g id="Edge_Cuts">
    <rect x="0" y="0" width="40" height="40" />
  </g>
  <g id="F_Cu">
    <line x1="5" y1="5" x2="35" y2="5" />
    <path d="M 5 20 A 5 5 0 0 1 15 20 L 25 20 C 27 20 30 25 30 30" />
    <polyline points="5,35 15,35 25,30" />
  </g>
  <g id="Drill">
    <circle cx="15" cy="20" r="0.8" />
  </g>
</svg>"""
    svg_file = tmp_path / "shapes.svg"
    svg_file.write_text(svg_content, encoding="utf-8")

    geom = parse_svg(svg_file, LayerMapping())
    assert geom.size == (40.0, 40.0)
    assert len(geom.traces) == 3
    assert len(geom.holes) == 1
    assert round(geom.holes[0].radius, 1) == 0.8


def test_generate_from_board_file_svg(tmp_path: Path):
    import shutil
    from pcb3d.config import LayerMapping
    from pcb3d.pipeline import generate_from_board_file

    if not shutil.which("openscad"):
        pytest.skip("OpenSCAD executable not available on PATH")

    svg_content = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="40mm" height="25mm" viewBox="0 0 40 25">
  <g id="Edge.Cuts">
    <polygon points="0,0 40,0 40,25 0,25" />
  </g>
  <g id="F.Cu">
    <path d="M 5 5 L 20 5 L 20 15" />
  </g>
  <g id="Drill">
    <circle cx="20" cy="15" r="1.0" />
  </g>
</svg>"""
    svg_file = tmp_path / "test_board.svg"
    svg_file.write_text(svg_content, encoding="utf-8")
    output_stl = tmp_path / "test_board.stl"

    out = generate_from_board_file(svg_file, output_stl, LayerMapping())
    assert out.is_file()
    assert out.stat().st_size > 0
    scad_content = output_stl.with_suffix(".scad").read_text()
    assert "difference()" in scad_content
    assert "cube([40.00000, 25.00000, base_thickness])" in scad_content


def test_cli_generate_with_svg_input(tmp_path: Path):
    import shutil
    from pcb3d.cli import main

    if not shutil.which("openscad"):
        pytest.skip("OpenSCAD executable not available on PATH")

    svg_content = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="30mm" height="20mm" viewBox="0 0 30 20">
  <g id="Edge.Cuts">
    <rect x="0" y="0" width="30" height="20" />
  </g>
  <g id="F.Cu">
    <line x1="5" y1="10" x2="25" y2="10" />
  </g>
  <g id="Drill">
    <circle cx="25" cy="10" r="0.8" />
  </g>
</svg>"""
    svg_file = tmp_path / "cli_board.svg"
    svg_file.write_text(svg_content, encoding="utf-8")
    output_stl = tmp_path / "cli_board.stl"

    exit_code = main(["generate", "-i", str(svg_file), "-o", str(output_stl)])
    assert exit_code == 0
    assert output_stl.is_file()
    assert output_stl.stat().st_size > 0




