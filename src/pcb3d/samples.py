"""Sample circuit board definitions with an indexed catalog of samples."""

from dataclasses import dataclass
import io
from typing import Callable

import ezdxf


@dataclass(frozen=True)
class SampleBoard:
    """Represents a predefined sample PCB board."""

    id: str
    name: str
    description: str
    generator: Callable[..., str]

    def to_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
        }


def generate_dip8_sample_dxf(*, m4_holes: bool = True) -> str:
    """Generate DXF content for a sample DIP-8 circuit board."""
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()

    # Board outline tightly sized to fit the circuit
    if m4_holes:
        width, height = 44.0, 28.0
        ox, oy = 6.0, 3.0
        # Corner M4 mounting holes (diameter 4.4mm, placed with 4.5mm corner margin)
        for x, y in [(4.5, 4.5), (39.5, 4.5), (39.5, 23.5), (4.5, 23.5)]:
            msp.add_circle((x, y), radius=2.2, dxfattribs={"layer": "NPTH"})
    else:
        width, height = 32.0, 22.0
        ox, oy = 0.0, 0.0

    msp.add_lwpolyline(
        [(0, 0), (width, 0), (width, height), (0, height)],
        close=True,
        dxfattribs={"layer": "Edge.Cuts"},
    )

    # Component / pin header holes (radius 0.5mm)
    # Left & right connector pads
    for x, y in [(ox + 5.0, oy + 8.5), (ox + 5.0, oy + 13.5), (ox + 27.0, oy + 8.5), (ox + 27.0, oy + 13.5)]:
        msp.add_circle((x, y), radius=0.5, dxfattribs={"layer": "Drill"})
    # DIP-8 component pin holes
    for i in range(4):
        px = ox + 12.0 + i * 2.54
        msp.add_circle((px, oy + 7.0), radius=0.5, dxfattribs={"layer": "Drill"})
        msp.add_circle((px, oy + 14.62), radius=0.5, dxfattribs={"layer": "Drill"})

    # Circuit traces: routed directly to hole centers so the trenches seamlessly connect into the holes
    msp.add_lwpolyline([(ox + 5.0, oy + 8.5), (ox + 8.0, oy + 8.5), (ox + 9.5, oy + 7.0), (ox + 12.0, oy + 7.0)], dxfattribs={"layer": "F.Cu"})
    msp.add_lwpolyline([(ox + 5.0, oy + 13.5), (ox + 8.0, oy + 13.5), (ox + 9.5, oy + 14.62), (ox + 12.0, oy + 14.62)], dxfattribs={"layer": "F.Cu"})
    msp.add_lwpolyline([(ox + 19.62, oy + 7.0), (ox + 22.5, oy + 7.0), (ox + 24.0, oy + 8.5), (ox + 27.0, oy + 8.5)], dxfattribs={"layer": "F.Cu"})
    msp.add_lwpolyline([(ox + 19.62, oy + 14.62), (ox + 22.5, oy + 14.62), (ox + 24.0, oy + 13.5), (ox + 27.0, oy + 13.5)], dxfattribs={"layer": "F.Cu"})
    msp.add_lwpolyline([(ox + 14.54, oy + 7.0), (ox + 14.54, oy + 3.5), (ox + 17.08, oy + 3.5), (ox + 17.08, oy + 7.0)], dxfattribs={"layer": "F.Cu"})
    msp.add_lwpolyline([(ox + 14.54, oy + 14.62), (ox + 14.54, oy + 18.2), (ox + 17.08, oy + 18.2), (ox + 17.08, oy + 14.62)], dxfattribs={"layer": "F.Cu"})
    msp.add_lwpolyline([(ox + 14.54, oy + 7.0), (ox + 15.81, oy + 7.5), (ox + 15.81, oy + 14.12), (ox + 14.54, oy + 14.62)], dxfattribs={"layer": "F.Cu"})

    stream = io.StringIO()
    doc.write(stream)
    return stream.getvalue()


# Indexed catalog of sample boards
SAMPLES: list[SampleBoard] = [
    SampleBoard(
        id="sample_pcb",
        name="Sample Circuit Board (DIP-8)",
        description="Dual connector pads with DIP-8 IC and routed front copper traces",
        generator=generate_dip8_sample_dxf,
    ),
]

SAMPLES_BY_ID: dict[str, SampleBoard] = {sample.id: sample for sample in SAMPLES}


def get_samples_catalog() -> list[dict[str, str]]:
    """Return an indexed list of sample descriptions for API and UI consumption."""
    return [sample.to_dict() for sample in SAMPLES]


def get_sample(sample_id_or_index: str | int | None = None) -> SampleBoard:
    """Retrieve a sample by its string ID or integer index, falling back to the first sample."""
    if sample_id_or_index is None:
        return SAMPLES[0]

    if isinstance(sample_id_or_index, int):
        if 0 <= sample_id_or_index < len(SAMPLES):
            return SAMPLES[sample_id_or_index]
        return SAMPLES[0]

    # Try numeric string
    if sample_id_or_index.isdigit():
        idx = int(sample_id_or_index)
        if 0 <= idx < len(SAMPLES):
            return SAMPLES[idx]

    # Try matching ID directly or aliases
    if sample_id_or_index in SAMPLES_BY_ID:
        return SAMPLES_BY_ID[sample_id_or_index]

    # Generic fallback
    return SAMPLES[0]
