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
    with pytest.raises(ValueError):
        GenerationParameters.from_mapping({"trace_width": 0})
    with pytest.raises(ValueError):
        GenerationParameters.from_mapping({"not_a_parameter": 1})


def test_config_accepts_strings_and_lists():
    mapping = mapping_from_dict({
        "layers": {"outline": "Board", "traces": ["CopperTop", "CopperBottom"], "holes": "Drill"},
        "parameters": {"base_thickness": 2},
    })
    assert mapping.outline == ("Board",)
    assert mapping.traces == ("CopperTop", "CopperBottom")
    assert mapping.parameters.base_thickness == 2


def test_openscad_source_contains_base_traces_and_through_hole():
    source = generate_openscad(simple_geometry(), GenerationParameters())
    assert "cube([20.00000, 20.00000, base_thickness])" in source
    assert "linear_extrude" in source
    assert "translate([0, 0, 1.60000])" in source
    assert "cylinder(h=base_thickness + 0.2" in source
    assert "difference()" in source


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
