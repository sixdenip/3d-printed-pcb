"""YAML configuration for layer selection and generation defaults."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .models import GenerationParameters


@dataclass(frozen=True)
class LayerMapping:
    outline: tuple[str, ...] = ("Edge.Cuts",)
    traces: tuple[str, ...] = ("F.Cu",)
    holes: tuple[str, ...] = ("NPTH", "Drill",)
    parameters: GenerationParameters = field(default_factory=GenerationParameters)

    def accepts(self, category: str, layer: str) -> bool:
        return layer in getattr(self, category)


def _layers(value: Any, default: tuple[str, ...]) -> tuple[str, ...]:
    if value is None:
        return default
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (list, tuple)) and all(isinstance(item, str) for item in value):
        return tuple(value)
    raise ValueError("Layer mappings must be a string or a list of strings")


def mapping_from_dict(data: dict[str, Any]) -> LayerMapping:
    layers = data.get("layers", data)
    if not isinstance(layers, dict):
        raise ValueError("'layers' must be a mapping")
    parameters = GenerationParameters.from_mapping(
        data.get("parameters", data.get("generation", {}))
    )
    return LayerMapping(
        outline=_layers(layers.get("outline"), ("Edge.Cuts",)),
        traces=_layers(layers.get("traces"), ("F.Cu",)),
        holes=_layers(layers.get("holes"), ("NPTH", "Drill")),
        parameters=parameters,
    )


def load_config(path: str | Path | None = None) -> LayerMapping:
    if path is None:
        return LayerMapping()
    config_path = Path(path)
    try:
        with config_path.open("r", encoding="utf-8") as stream:
            data = yaml.safe_load(stream) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"Cannot read config '{config_path}': {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("Configuration root must be a YAML mapping")
    return mapping_from_dict(data)
