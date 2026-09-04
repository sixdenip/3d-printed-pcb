"""DXF to normalized geometry conversion using ezdxf."""

from pathlib import Path
import math
from typing import Any, Iterable

import ezdxf

from .config import LayerMapping
from .models import BoardGeometry, Hole, Point, Polyline


class DxfParseError(ValueError):
    """Raised when the DXF cannot be converted to board geometry."""


def _layer(entity: Any) -> str:
    return str(entity.dxf.layer)


def _points(entity: Any) -> tuple[Point, ...]:
    kind = entity.dxftype()
    if kind == "LINE":
        return (
            Point(float(entity.dxf.start.x), float(entity.dxf.start.y)),
            Point(float(entity.dxf.end.x), float(entity.dxf.end.y)),
        )
    if kind == "LWPOLYLINE":
        return tuple(Point(float(x), float(y)) for x, y, *_ in entity.get_points("xy"))
    if kind == "POLYLINE":
        return tuple(Point(float(vertex.dxf.location.x), float(vertex.dxf.location.y))
                     for vertex in entity.vertices)
    if kind == "ARC":
        center = entity.dxf.center
        radius = float(entity.dxf.radius)
        start = float(entity.dxf.start_angle)
        end = float(entity.dxf.end_angle)
        while end <= start:
            end += 360
        count = max(4, min(128, math.ceil((end - start) / 10)))
        return tuple(
            Point(
                float(center.x) + radius * math.cos(math.radians(start + i * (end - start) / count)),
                float(center.y) + radius * math.sin(math.radians(start + i * (end - start) / count)),
            )
            for i in range(count + 1)
        )
    raise DxfParseError(f"Unsupported outline/trace entity type: {kind}")


def _polyline(entity: Any) -> Polyline:
    points = _points(entity)
    if len(points) < 2:
        raise DxfParseError(f"{entity.dxftype()} has fewer than two points")
    flags = int(getattr(entity.dxf, "flags", 0))
    closed = bool(getattr(entity, "closed", False) or flags & 1)
    if entity.dxftype() == "LWPOLYLINE":
        closed = bool(entity.closed)
    return Polyline(points, closed)


def _iter_entities(document: Any) -> Iterable[Any]:
    return document.modelspace()


def parse_dxf(source: str | Path, mapping: LayerMapping) -> BoardGeometry:
    """Parse a file path into outline, centerline traces, and circular holes."""
    try:
        document = ezdxf.readfile(str(source))
    except (OSError, IOError, ezdxf.DXFError) as exc:
        raise DxfParseError(f"Cannot read DXF '{source}': {exc}") from exc

    outlines: list[Polyline] = []
    traces: list[Polyline] = []
    holes: list[Hole] = []
    for entity in _iter_entities(document):
        layer = _layer(entity)
        kind = entity.dxftype()
        if mapping.accepts("outline", layer) and kind in {"LINE", "LWPOLYLINE", "POLYLINE", "ARC"}:
            outlines.append(_polyline(entity))
        elif mapping.accepts("traces", layer) and kind in {"LINE", "LWPOLYLINE", "POLYLINE", "ARC"}:
            traces.append(_polyline(entity))
        elif mapping.accepts("holes", layer) and kind == "CIRCLE":
            center = entity.dxf.center
            holes.append(Hole(Point(float(center.x), float(center.y)), float(entity.dxf.radius)))

    if not outlines:
        raise DxfParseError(
            f"No outline found on configured layer(s): {', '.join(mapping.outline)}"
        )
    if len(outlines) > 1:
        # An outline may be exported as segments; joining is deliberately avoided
        # because OpenSCAD only needs its bounding rectangle for this MVP.
        outline = Polyline(
            tuple(point for line in outlines for point in line.points),
            closed=False,
        )
    else:
        outline = outlines[0]
    return BoardGeometry(outline=outline, traces=tuple(traces), holes=tuple(holes))
