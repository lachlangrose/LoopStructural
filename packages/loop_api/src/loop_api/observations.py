from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from loop_common.observations import LineSet, Orientation, PointSet


def _as_array(data: Any, shape_last: int | None = None) -> np.ndarray:
    arr = np.asarray(data, dtype=float)
    if shape_last is not None and arr.shape[-1] != shape_last:
        raise ValueError(f"Expected last dimension {shape_last}, got shape {arr.shape}")
    return arr


def _load_table_records(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return [dict(r) for r in reader]


def _load_structured_file(path: Path) -> dict[str, Any]:
    suffix = path.suffix.lower()
    if suffix in {".yml", ".yaml"}:
        with path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    if suffix == ".json":
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    raise ValueError(f"Unsupported structured file format: {path}")


def _pointset_from_file(path: Path) -> PointSet:
    if path.suffix.lower() in {".yaml", ".yml", ".json"}:
        payload = _load_structured_file(path)
        return _pointset_from_inline(payload)

    records = _load_table_records(path)
    coords = np.array([[float(r["x"]), float(r["y"]), float(r["z"])] for r in records], dtype=float)
    return PointSet(coords=coords)


def _orientation_from_file(path: Path) -> Orientation:
    if path.suffix.lower() in {".yaml", ".yml", ".json"}:
        payload = _load_structured_file(path)
        return _orientation_from_inline(payload)

    records = _load_table_records(path)
    coords = np.array([[float(r["x"]), float(r["y"]), float(r["z"])] for r in records], dtype=float)
    vector = np.array(
        [[float(r["gx"]), float(r["gy"]), float(r["gz"])] for r in records],
        dtype=float,
    )
    magnitude = np.array([float(r.get("magnitude", 1.0)) for r in records], dtype=float)
    polarity = np.array([float(r.get("polarity", 1.0)) for r in records], dtype=float)
    obs_type = records[0].get("type", "plane") if records else "plane"
    return Orientation(coords=coords, vector=vector, magnitude=magnitude, polarity=polarity, type=obs_type)


def _lineset_from_file(path: Path) -> LineSet:
    if path.suffix.lower() in {".yaml", ".yml", ".json"}:
        payload = _load_structured_file(path)
        return _lineset_from_inline(payload)

    records = _load_table_records(path)
    vertices = np.array([[float(r["x"]), float(r["y"]), float(r["z"])] for r in records], dtype=float)
    offsets = [0]

    if records and "line_id" in records[0]:
        current = records[0]["line_id"]
        for i, record in enumerate(records):
            line_id = record["line_id"]
            if i > 0 and line_id != current:
                offsets.append(i)
                current = line_id
    offsets.append(len(records))

    return LineSet(vertices=vertices, offsets=np.array(offsets, dtype=int))


def _pointset_from_inline(payload: dict[str, Any]) -> PointSet:
    return PointSet(coords=_as_array(payload["coords"], shape_last=3))


def _orientation_from_inline(payload: dict[str, Any]) -> Orientation:
    coords = _as_array(payload["coords"], shape_last=3)
    vector = _as_array(payload["vector"], shape_last=3)
    n = coords.shape[0]

    magnitude = _as_array(payload.get("magnitude", np.ones(n)))
    polarity = _as_array(payload.get("polarity", np.ones(n)))
    obs_type = payload.get("type", "plane")

    return Orientation(coords=coords, vector=vector, magnitude=magnitude, polarity=polarity, type=obs_type)


def _lineset_from_inline(payload: dict[str, Any]) -> LineSet:
    vertices = _as_array(payload["vertices"], shape_last=3)
    offsets = np.asarray(payload["offsets"], dtype=int)
    return LineSet(vertices=vertices, offsets=offsets)


def load_observation(observation_spec: dict[str, Any], context: dict[str, Any]):
    source_dir: Path | None = context.get("source_dir")
    obs_type = str(observation_spec["type"]).lower()

    if "inline" in observation_spec:
        payload = observation_spec["inline"]
        if obs_type == "pointset":
            return _pointset_from_inline(payload)
        if obs_type == "orientation":
            return _orientation_from_inline(payload)
        if obs_type == "lineset":
            return _lineset_from_inline(payload)
        raise ValueError(f"Unsupported observation type: {obs_type}")

    if "file" in observation_spec:
        if source_dir is None:
            raise ValueError("Cannot resolve file-backed observation without source_dir")
        path = (source_dir / observation_spec["file"]).resolve()
        if obs_type == "pointset":
            return _pointset_from_file(path)
        if obs_type == "orientation":
            return _orientation_from_file(path)
        if obs_type == "lineset":
            return _lineset_from_file(path)
        raise ValueError(f"Unsupported observation type: {obs_type}")

    raise ValueError("Observation must provide either inline or file payload")
