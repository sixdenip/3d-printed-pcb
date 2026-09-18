"""Small, dependency-free normalized geometry and parameter types."""

from dataclasses import dataclass, field
import math
from typing import Sequence


@dataclass(frozen=True)
class Point:
    x: float
    y: float

    def shifted(self, dx: float, dy: float) -> "Point":
        return Point(self.x + dx, self.y + dy)


@dataclass(frozen=True)
class Polyline:
    points: tuple[Point, ...]
    closed: bool = False

    def __post_init__(self) -> None:
        if len(self.points) < 2:
            raise ValueError("A polyline needs at least two points")


@dataclass(frozen=True)
class Hole:
    center: Point
    radius: float

    def __post_init__(self) -> None:
        if self.radius <= 0:
            raise ValueError("Hole radius must be positive")


@dataclass(frozen=True)
class BoardGeometry:
    """Geometry normalized to millimetres, with coordinates in DXF space."""

    outline: Polyline
    traces: tuple[Polyline, ...] = field(default_factory=tuple)
    holes: tuple[Hole, ...] = field(default_factory=tuple)

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        points = self.outline.points
        return (
            min(point.x for point in points),
            min(point.y for point in points),
            max(point.x for point in points),
            max(point.y for point in points),
        )

    @property
    def size(self) -> tuple[float, float]:
        left, bottom, right, top = self.bounds
        return right - left, top - bottom

    def translated_to_origin(self) -> "BoardGeometry":
        left, bottom, _, _ = self.bounds
        move = lambda point: point.shifted(-left, -bottom)
        return BoardGeometry(
            outline=Polyline(tuple(move(p) for p in self.outline.points), self.outline.closed),
            traces=tuple(
                Polyline(tuple(move(p) for p in trace.points), trace.closed)
                for trace in self.traces
            ),
            holes=tuple(Hole(move(hole.center), hole.radius) for hole in self.holes),
        )


    def connect_traces_to_holes(self, snap_tolerance: float = 0.5) -> "BoardGeometry":
        """Snap open trace endpoints within (hole.radius + snap_tolerance) to the hole center."""
        if not self.holes or not self.traces or snap_tolerance < 0:
            return self

        new_traces: list[Polyline] = []
        for trace in self.traces:
            if trace.closed or len(trace.points) < 2:
                new_traces.append(trace)
                continue

            points = list(trace.points)

            # Snap start point to nearest through-hole if within reach
            p_start = points[0]
            closest_hole_start = None
            min_dist_start = float("inf")
            for hole in self.holes:
                d = math.hypot(p_start.x - hole.center.x, p_start.y - hole.center.y)
                if d <= hole.radius + snap_tolerance and d < min_dist_start:
                    min_dist_start = d
                    closest_hole_start = hole

            # Snap end point to nearest through-hole if within reach
            p_end = points[-1]
            closest_hole_end = None
            min_dist_end = float("inf")
            for hole in self.holes:
                d = math.hypot(p_end.x - hole.center.x, p_end.y - hole.center.y)
                if d <= hole.radius + snap_tolerance and d < min_dist_end:
                    min_dist_end = d
                    closest_hole_end = hole

            # Guard against collapsing a 2-point trace into a single duplicate point
            if (
                closest_hole_start is not None
                and closest_hole_end is not None
                and closest_hole_start == closest_hole_end
                and len(points) == 2
            ):
                new_traces.append(trace)
                continue

            if closest_hole_start is not None:
                points[0] = closest_hole_start.center
            if closest_hole_end is not None:
                points[-1] = closest_hole_end.center

            new_traces.append(Polyline(tuple(points), trace.closed))

        return BoardGeometry(
            outline=self.outline,
            traces=tuple(new_traces),
            holes=self.holes,
        )


@dataclass(frozen=True)
class GenerationParameters:
    base_thickness: float = 1.6
    trace_height: float = 0.4
    trace_width: float = 0.4
    outline_margin: float = 0.0
    snap_tolerance: float = 0.5

    @property
    def trace_depth(self) -> float:
        return self.trace_height

    def validate(self) -> "GenerationParameters":
        values = {
            "base_thickness": self.base_thickness,
            "trace_height": self.trace_height,
            "trace_width": self.trace_width,
            "outline_margin": self.outline_margin,
            "snap_tolerance": self.snap_tolerance,
        }
        for name, value in values.items():
            non_negative = name in {"outline_margin", "snap_tolerance"}
            if not math.isfinite(value) or value < 0 or (not non_negative and value == 0):
                requirement = "non-negative" if non_negative else "positive"
                raise ValueError(f"{name} must be {requirement}")
        # Prevent trenches from cutting entirely through or below the substrate
        if self.trace_height >= self.base_thickness:
            raise ValueError("trace_height (trench depth) must be less than base_thickness")
        return self

    @classmethod
    def from_mapping(cls, values: dict[str, object] | None) -> "GenerationParameters":
        values = dict(values) if values else {}
        if "trace_depth" in values and "trace_height" not in values:
            values["trace_height"] = values.pop("trace_depth")
        allowed = {
            "base_thickness", "trace_height", "trace_depth",
            "trace_width", "outline_margin", "snap_tolerance"
        }
        unknown = set(values) - allowed
        if unknown:
            raise ValueError(f"Unknown generation parameter(s): {', '.join(sorted(unknown))}")
        try:
            params = cls(**{
                key: float(value)
                for key, value in values.items()
                if key in {"base_thickness", "trace_height", "trace_width", "outline_margin", "snap_tolerance"}
            })
        except (TypeError, ValueError) as exc:
            raise ValueError("Generation parameters must be numeric") from exc
        return params.validate()



def points_from_pairs(values: Sequence[Sequence[float]]) -> tuple[Point, ...]:
    return tuple(Point(float(pair[0]), float(pair[1])) for pair in values)
