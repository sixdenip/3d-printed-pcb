"""SVG to normalized geometry conversion for KiCad and standard CAD vector exports."""

from pathlib import Path
import math
import re
from typing import Any
import xml.etree.ElementTree as ET

from .config import LayerMapping
from .models import BoardGeometry, Hole, Point, Polyline


class SvgParseError(ValueError):
    """Raised when the SVG file cannot be parsed or converted to board geometry."""


def _parse_unit_to_mm(val_str: str | None) -> float | None:
    """Parse an SVG length string into millimetres."""
    if not val_str:
        return None
    val_str = val_str.strip()
    match = re.match(r"^([-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?)\s*([a-zA-Z%]*)$", val_str)
    if not match:
        return None
    val = float(match.group(1))
    unit = match.group(2).lower()
    if unit in ("mm", ""):
        return val
    elif unit == "cm":
        return val * 10.0
    elif unit == "in":
        return val * 25.4
    elif unit == "pt":
        return val * 25.4 / 72.0
    elif unit == "px":
        return val * 25.4 / 96.0  # CSS standard 96 DPI
    return val


def _arc_to_points(
    x1: float, y1: float,
    rx: float, ry: float,
    phi_deg: float,
    large_arc: float,
    sweep: float,
    x2: float, y2: float,
    segments: int = 8,
) -> list[tuple[float, float]]:
    """Convert an SVG elliptical arc into discrete 2D polyline points."""
    if rx == 0 or ry == 0:
        return [(x2, y2)]
    rx = abs(rx)
    ry = abs(ry)
    phi = math.radians(phi_deg % 360)
    cos_phi = math.cos(phi)
    sin_phi = math.sin(phi)

    dx = (x1 - x2) / 2.0
    dy = (y1 - y2) / 2.0
    x1_p = cos_phi * dx + sin_phi * dy
    y1_p = -sin_phi * dx + cos_phi * dy

    lam = (x1_p**2) / (rx**2) + (y1_p**2) / (ry**2)
    if lam > 1.0:
        s = math.sqrt(lam)
        rx *= s
        ry *= s

    sign = -1.0 if large_arc == sweep else 1.0
    radicand = max(0.0, (rx**2 * ry**2 - rx**2 * y1_p**2 - ry**2 * x1_p**2) / (rx**2 * y1_p**2 + ry**2 * x1_p**2))
    coef = sign * math.sqrt(radicand)
    cx_p = coef * ((rx * y1_p) / ry)
    cy_p = coef * (-(ry * x1_p) / rx)

    cx = cos_phi * cx_p - sin_phi * cy_p + (x1 + x2) / 2.0
    cy = sin_phi * cx_p + cos_phi * cy_p + (y1 + y2) / 2.0

    def _angle(ux: float, uy: float, vx: float, vy: float) -> float:
        dot = ux * vx + uy * vy
        denom = math.hypot(ux, uy) * math.hypot(vx, vy)
        if denom == 0:
            return 0.0
        val = max(-1.0, min(1.0, dot / denom))
        ang = math.acos(val)
        if ux * vy - uy * vx < 0:
            ang = -ang
        return ang

    ux = (x1_p - cx_p) / rx
    uy = (y1_p - cy_p) / ry
    vx = (-x1_p - cx_p) / rx
    vy = (-y1_p - cy_p) / ry

    theta1 = _angle(1, 0, ux, uy)
    d_theta = _angle(ux, uy, vx, vy) % (2 * math.pi)
    if not sweep and d_theta > 0:
        d_theta -= 2 * math.pi
    elif sweep and d_theta < 0:
        d_theta += 2 * math.pi

    pts: list[tuple[float, float]] = []
    num_pts = max(2, int(segments * abs(d_theta) / math.pi))
    for s in range(1, num_pts + 1):
        ang = theta1 + d_theta * (s / num_pts)
        ex = rx * math.cos(ang)
        ey = ry * math.sin(ang)
        px = cos_phi * ex - sin_phi * ey + cx
        py = sin_phi * ex + cos_phi * ey + cy
        pts.append((px, py))
    return pts


def _tokenize_path(d: str) -> list[str | float]:
    """Tokenize SVG path 'd' attribute into commands and numeric arguments."""
    raw = re.findall(r'([a-df-z]|[-+]?(?:[0-9]*\.[0-9]+|[0-9]+)(?:[eE][-+]?[0-9]+)?)', d, re.IGNORECASE)
    tokens: list[str | float] = []
    for token in raw:
        if token.isalpha():
            tokens.append(token)
        else:
            try:
                tokens.append(float(token))
            except ValueError:
                continue
    return tokens


def _parse_path_polylines(
    d: str, scale_x: float, scale_y: float
) -> list[tuple[tuple[Point, ...], bool]]:
    """Parse an SVG path 'd' attribute into distinct (points, is_closed) subpaths."""
    tokens = _tokenize_path(d)
    polylines: list[tuple[tuple[Point, ...], bool]] = []
    current_pts: list[tuple[float, float]] = []
    curr_x, curr_y = 0.0, 0.0
    start_x, start_y = 0.0, 0.0
    last_ctrl_x, last_ctrl_y = 0.0, 0.0
    i = 0
    cmd: str | None = None

    def _flush(closed: bool = False) -> None:
        nonlocal current_pts
        if len(current_pts) >= 2:
            # Note: Invert Y so SVG (+y down) matches standard CAD Cartesian space (+y up)
            points = tuple(Point(px * scale_x, -py * scale_y) for px, py in current_pts)
            polylines.append((points, closed))
        current_pts = []

    while i < len(tokens):
        item = tokens[i]
        if isinstance(item, str):
            cmd = item
            i += 1
        if cmd is None:
            break

        if cmd == 'M':
            if len(current_pts) >= 2:
                _flush(False)
            curr_x = float(tokens[i])
            curr_y = float(tokens[i+1])
            start_x, start_y = curr_x, curr_y
            current_pts = [(curr_x, curr_y)]
            last_ctrl_x, last_ctrl_y = curr_x, curr_y
            i += 2
            cmd = 'L'  # Implicit successive coordinates
        elif cmd == 'm':
            if len(current_pts) >= 2:
                _flush(False)
            curr_x += float(tokens[i])
            curr_y += float(tokens[i+1])
            start_x, start_y = curr_x, curr_y
            current_pts = [(curr_x, curr_y)]
            last_ctrl_x, last_ctrl_y = curr_x, curr_y
            i += 2
            cmd = 'l'
        elif cmd == 'L':
            curr_x = float(tokens[i])
            curr_y = float(tokens[i+1])
            current_pts.append((curr_x, curr_y))
            last_ctrl_x, last_ctrl_y = curr_x, curr_y
            i += 2
        elif cmd == 'l':
            curr_x += float(tokens[i])
            curr_y += float(tokens[i+1])
            current_pts.append((curr_x, curr_y))
            last_ctrl_x, last_ctrl_y = curr_x, curr_y
            i += 2
        elif cmd == 'H':
            curr_x = float(tokens[i])
            current_pts.append((curr_x, curr_y))
            last_ctrl_x, last_ctrl_y = curr_x, curr_y
            i += 1
        elif cmd == 'h':
            curr_x += float(tokens[i])
            current_pts.append((curr_x, curr_y))
            last_ctrl_x, last_ctrl_y = curr_x, curr_y
            i += 1
        elif cmd == 'V':
            curr_y = float(tokens[i])
            current_pts.append((curr_x, curr_y))
            last_ctrl_x, last_ctrl_y = curr_x, curr_y
            i += 1
        elif cmd == 'v':
            curr_y += float(tokens[i])
            current_pts.append((curr_x, curr_y))
            last_ctrl_x, last_ctrl_y = curr_x, curr_y
            i += 1
        elif cmd in ('C', 'c'):
            is_rel = cmd == 'c'
            x1 = curr_x + float(tokens[i]) if is_rel else float(tokens[i])
            y1 = curr_y + float(tokens[i+1]) if is_rel else float(tokens[i+1])
            x2 = curr_x + float(tokens[i+2]) if is_rel else float(tokens[i+2])
            y2 = curr_y + float(tokens[i+3]) if is_rel else float(tokens[i+3])
            x = curr_x + float(tokens[i+4]) if is_rel else float(tokens[i+4])
            y = curr_y + float(tokens[i+5]) if is_rel else float(tokens[i+5])
            for step in range(1, 7):
                t = step / 6.0
                bx = (1-t)**3 * curr_x + 3*(1-t)**2*t * x1 + 3*(1-t)*t**2 * x2 + t**3 * x
                by = (1-t)**3 * curr_y + 3*(1-t)**2*t * y1 + 3*(1-t)*t**2 * y2 + t**3 * y
                current_pts.append((bx, by))
            last_ctrl_x, last_ctrl_y = x2, y2
            curr_x, curr_y = x, y
            i += 6
        elif cmd in ('S', 's'):
            is_rel = cmd == 's'
            # Reflect last control point
            x1 = 2 * curr_x - last_ctrl_x
            y1 = 2 * curr_y - last_ctrl_y
            x2 = curr_x + float(tokens[i]) if is_rel else float(tokens[i])
            y2 = curr_y + float(tokens[i+1]) if is_rel else float(tokens[i+1])
            x = curr_x + float(tokens[i+2]) if is_rel else float(tokens[i+2])
            y = curr_y + float(tokens[i+3]) if is_rel else float(tokens[i+3])
            for step in range(1, 7):
                t = step / 6.0
                bx = (1-t)**3 * curr_x + 3*(1-t)**2*t * x1 + 3*(1-t)*t**2 * x2 + t**3 * x
                by = (1-t)**3 * curr_y + 3*(1-t)**2*t * y1 + 3*(1-t)*t**2 * y2 + t**3 * y
                current_pts.append((bx, by))
            last_ctrl_x, last_ctrl_y = x2, y2
            curr_x, curr_y = x, y
            i += 4
        elif cmd in ('A', 'a'):
            is_rel = cmd == 'a'
            rx = float(tokens[i])
            ry = float(tokens[i+1])
            rot = float(tokens[i+2])
            large_arc = float(tokens[i+3])
            sweep = float(tokens[i+4])
            x = curr_x + float(tokens[i+5]) if is_rel else float(tokens[i+5])
            y = curr_y + float(tokens[i+6]) if is_rel else float(tokens[i+6])
            arc_pts = _arc_to_points(curr_x, curr_y, rx, ry, rot, large_arc, sweep, x, y)
            current_pts.extend(arc_pts)
            last_ctrl_x, last_ctrl_y = x, y
            curr_x, curr_y = x, y
            i += 7
        elif cmd in ('Z', 'z'):
            if len(current_pts) >= 2:
                if current_pts[0] != current_pts[-1]:
                    current_pts.append((start_x, start_y))
                _flush(True)
            curr_x, curr_y = start_x, start_y
            last_ctrl_x, last_ctrl_y = curr_x, curr_y
            cmd = None
        else:
            i += 1

    _flush(False)
    return polylines


def _matches_layer(mapping: LayerMapping, role: str, name: str | None) -> bool:
    """Check if a layer name matches configured layers (handling KiCad dot/underscore conventions)."""
    if not name:
        return False
    candidates = [
        name,
        name.lower(),
        name.replace("_", "."),
        name.replace(".", "_"),
        name.replace("-", "."),
    ]
    for c in candidates:
        if mapping.accepts(role, c):
            return True
    return False


def parse_svg(source: str | Path, mapping: LayerMapping) -> BoardGeometry:
    """Parse a KiCad or CAD exported SVG file into normalized BoardGeometry."""
    path = Path(source)
    try:
        tree = ET.parse(str(path))
        root = tree.getroot()
    except Exception as exc:
        raise SvgParseError(f"Cannot parse SVG '{source}': {exc}") from exc

    # Determine document scaling to millimetres
    raw_width = root.attrib.get("width")
    raw_height = root.attrib.get("height")
    raw_viewbox = root.attrib.get("viewBox") or root.attrib.get("viewbox")

    scale_x = 1.0
    scale_y = 1.0

    width_mm = _parse_unit_to_mm(raw_width)
    height_mm = _parse_unit_to_mm(raw_height)

    if raw_viewbox:
        vb_parts = [float(p) for p in re.split(r"[\s,]+", raw_viewbox.strip()) if p]
        if len(vb_parts) == 4:
            _, _, vb_w, vb_h = vb_parts
            if width_mm and vb_w > 0:
                scale_x = width_mm / vb_w
            if height_mm and vb_h > 0:
                scale_y = height_mm / vb_h
    elif width_mm or height_mm:
        if width_mm:
            scale_x = 1.0
        if height_mm:
            scale_y = 1.0

    outlines: list[Polyline] = []
    traces: list[Polyline] = []
    holes: list[Hole] = []

    def _process_element(elem: ET.Element, active_layer: str | None) -> None:
        tag = elem.tag.split("}")[-1].lower()
        elem_layer = elem.attrib.get("id") or elem.attrib.get("class") or active_layer

        is_outline = _matches_layer(mapping, "outline", elem_layer)
        is_traces = _matches_layer(mapping, "traces", elem_layer)
        is_holes = _matches_layer(mapping, "holes", elem_layer)

        if tag == "circle":
            try:
                cx = float(elem.attrib.get("cx", 0)) * scale_x
                cy = -float(elem.attrib.get("cy", 0)) * scale_y
                r = float(elem.attrib.get("r", 0)) * ((scale_x + scale_y) / 2.0)
                if r > 0:
                    hole = Hole(center=Point(cx, cy), radius=r)
                    if is_outline:
                        # Circle used as outline: convert to circular polyline
                        pts = tuple(
                            Point(cx + r * math.cos(i * math.pi / 16), cy + r * math.sin(i * math.pi / 16))
                            for i in range(33)
                        )
                        outlines.append(Polyline(pts, closed=True))
                    else:
                        holes.append(hole)
            except Exception:
                pass

        elif tag == "rect":
            try:
                x = float(elem.attrib.get("x", 0)) * scale_x
                y = -float(elem.attrib.get("y", 0)) * scale_y
                w = float(elem.attrib.get("width", 0)) * scale_x
                h = -float(elem.attrib.get("height", 0)) * scale_y
                rect_pts = (
                    Point(x, y),
                    Point(x + w, y),
                    Point(x + w, y + h),
                    Point(x, y + h),
                    Point(x, y),
                )
                poly = Polyline(rect_pts, closed=True)
                if is_outline or (not is_traces and not is_holes):
                    outlines.append(poly)
                elif is_traces:
                    traces.append(poly)
            except Exception:
                pass

        elif tag in ("line", "polyline", "polygon"):
            try:
                pts: list[Point] = []
                if tag == "line":
                    x1 = float(elem.attrib.get("x1", 0)) * scale_x
                    y1 = -float(elem.attrib.get("y1", 0)) * scale_y
                    x2 = float(elem.attrib.get("x2", 0)) * scale_x
                    y2 = -float(elem.attrib.get("y2", 0)) * scale_y
                    pts = [Point(x1, y1), Point(x2, y2)]
                    closed = False
                else:
                    raw_pts = re.split(r"[\s,]+", elem.attrib.get("points", "").strip())
                    nums = [float(p) for p in raw_pts if p]
                    pts = [Point(nums[j] * scale_x, -nums[j+1] * scale_y) for j in range(0, len(nums) - 1, 2)]
                    closed = (tag == "polygon")

                if len(pts) >= 2:
                    poly = Polyline(tuple(pts), closed=closed)
                    if is_outline:
                        outlines.append(poly)
                    elif is_traces:
                        traces.append(poly)
                    elif not is_holes:
                        if closed and not outlines:
                            outlines.append(poly)
                        else:
                            traces.append(poly)
            except Exception:
                pass

        elif tag == "path":
            d = elem.attrib.get("d")
            if d:
                parsed_subpaths = _parse_path_polylines(d, scale_x, scale_y)
                for pts, closed in parsed_subpaths:
                    if len(pts) < 2:
                        continue
                    # Check if this subpath on a holes layer represents a circular hole
                    if is_holes:
                        min_x = min(p.x for p in pts)
                        max_x = max(p.x for p in pts)
                        min_y = min(p.y for p in pts)
                        max_y = max(p.y for p in pts)
                        span_x = max_x - min_x
                        span_y = max_y - min_y
                        if span_x > 0 and abs(span_x - span_y) / span_x < 0.2:
                            radius = (span_x + span_y) / 4.0
                            center = Point((min_x + max_x) / 2.0, (min_y + max_y) / 2.0)
                            holes.append(Hole(center=center, radius=radius))
                            continue

                    poly = Polyline(pts, closed=closed)
                    if is_outline:
                        outlines.append(poly)
                    elif is_traces:
                        traces.append(poly)
                    elif is_holes:
                        pass
                    else:
                        # Fallback heuristic: closed polygons before outline is found
                        if closed and not outlines:
                            outlines.append(poly)
                        else:
                            traces.append(poly)

    def _traverse(elem: ET.Element, current_layer: str | None = None) -> None:
        tag = elem.tag.split("}")[-1].lower()
        elem_layer = elem.attrib.get("id") or elem.attrib.get("class") or current_layer
        if tag in ("svg", "g"):
            for child in elem:
                _traverse(child, elem_layer)
        else:
            _process_element(elem, elem_layer)

    _traverse(root)

    if not outlines:
        # If no explicit outline was identified by layer name, synthesize an outline from all geometry bounds
        all_pts: list[Point] = []
        for t in traces:
            all_pts.extend(t.points)
        for h in holes:
            all_pts.extend([
                Point(h.center.x - h.radius, h.center.y),
                Point(h.center.x + h.radius, h.center.y),
                Point(h.center.x, h.center.y - h.radius),
                Point(h.center.x, h.center.y + h.radius),
            ])
        if all_pts:
            min_x = min(p.x for p in all_pts) - 1.0
            max_x = max(p.x for p in all_pts) + 1.0
            min_y = min(p.y for p in all_pts) - 1.0
            max_y = max(p.y for p in all_pts) + 1.0
            outlines.append(Polyline(
                (Point(min_x, min_y), Point(max_x, min_y), Point(max_x, max_y), Point(min_x, max_y), Point(min_x, min_y)),
                closed=True,
            ))
        else:
            raise SvgParseError(
                f"No outline or circuit elements found in SVG '{source}'"
            )

    if len(outlines) > 1:
        # Merge outline points for bounding box computation
        outline = Polyline(
            tuple(point for line in outlines for point in line.points),
            closed=False,
        )
    else:
        outline = outlines[0]

    return BoardGeometry(outline=outline, traces=tuple(traces), holes=tuple(holes))
