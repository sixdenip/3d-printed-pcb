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


@dataclass(frozen=True)
class GenerationParameters:
    base_thickness: float = 1.6
    trace_height: float = 0.4
    trace_width: float = 0.4
    outline_margin: float = 0.0

    def validate(self) -> "GenerationParameters":
        values = {
            "base_thickness": self.base_thickness,
            "trace_height": self.trace_height,
            "trace_width": self.trace_width,
            "outline_margin": self.outline_margin,
        }
        for name, value in values.items():
            if not math.isfinite(value) or value < 0 or (name != "outline_margin" and value == 0):
                requirement = "non-negative" if name == "outline_margin" else "positive"
                raise ValueError(f"{name} must be {requirement}")
        return self

    @classmethod
    def from_mapping(cls, values: dict[str, object] | None) -> "GenerationParameters":
        values = values or {}
        allowed = {"base_thickness", "trace_height", "trace_width", "outline_margin"}
        unknown = set(values) - allowed
        if unknown:
            raise ValueError(f"Unknown generation parameter(s): {', '.join(sorted(unknown))}")
        try:
            params = cls(**{key: float(value) for key, value in values.items()})
        except (TypeError, ValueError) as exc:
            raise ValueError("Generation parameters must be numeric") from exc
        return params.validate()


def points_from_pairs(values: Sequence[Sequence[float]]) -> tuple[Point, ...]:
    return tuple(Point(float(pair[0]), float(pair[1])) for pair in values)
