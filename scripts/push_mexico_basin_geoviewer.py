"""Send exported Mexico Basin cases and their source constraints through loop-link.

Run with GEOVIEWER_TOKEN in the environment. No token is saved. The uploader
only creates/replaces its own mexico-basin namespace and preserves other
viewer objects. All coordinates remain EPSG:32614 in metres.

The input constraints are the original present-day contact points and
section-derived orientations submitted to the example, before restoration.
Displacement cutoff pairs are provided as a separate kind of constraint.
No modelling or source downloads occur here; the source cache must exist.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pandas as pd
import pyvista as pv

ROOT = Path(__file__).resolve().parents[1]
NAMESPACE = "loopstructural/mexico-basin"


def load_example() -> ModuleType:
    """Import the model's input reader without rebuilding geological models."""
    path = ROOT / "examples/5_case_studies/plot_2_mexico_basin.py"
    spec = importlib.util.spec_from_file_location("mexico_basin_demo", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def rgb(colour: str) -> tuple[int, ...]:
    """Convert a hexadecimal model colour to RGB bytes."""
    return tuple(int(colour[i : i + 2], 16) for i in (1, 3, 5))


def categorical(values: pd.Series, cls: type) -> object:
    """Keep source labels as explicit, inspectable categorical properties."""
    labels = pd.Series(values).fillna("unknown").astype(str)
    codes, names = pd.factorize(labels, sort=True)
    return cls(codes.astype(np.uint32), list(names))


def objects_for_zone(
    example: ModuleType, zone: str, directory: Path, constraints_directory: Path
) -> dict[str, Any]:
    """Prepare every object before connecting to the running viewer."""
    from loop_link import BlockModel, Categorical, Lines, Points, Surface, Vectors

    metadata = json.loads((directory / "model.json").read_text(encoding="utf-8"))
    if metadata["source_commit"] != example.COMMIT:
        raise ValueError(f"The {zone} export uses a different source commit")
    inputs = example.load_inputs(zone, offline=True)
    contacts = inputs.contacts.drop_duplicates(subset=["formation", *example.XYZ])
    orientations = inputs.orientations.drop_duplicates(
        subset=["formation", *example.XYZ, "dip", "azimuth"]
    )
    grid = pv.read(directory / "implicit_fields.vts")
    dimensions = np.asarray(metadata["dimensions"], dtype=int)
    if tuple(grid.dimensions) != tuple(dimensions):
        raise ValueError(f"The {zone} grid does not match its manifest")
    names = metadata["units"]
    unit_ids = np.asarray(grid.cell_data["unit_id"], dtype=np.int32)
    colours = [(0, 0, 0, 0)] + [(*rgb(example.COLOURS[name]), 255) for name in names]
    properties = {
        name: np.asarray(grid.point_data[name])
        for name in grid.point_data
        if np.asarray(grid.point_data[name]).ndim == 1
    }
    # Keep displacement magnitudes inspectable without sending vector-valued
    # properties, which loop-link's scalar property protocol does not accept.
    for name in grid.point_data:
        if name.startswith("restoration_"):
            properties[name + "_magnitude_m"] = np.linalg.norm(grid.point_data[name], axis=1)
    block = BlockModel(
        origin=metadata["origin"],
        cell_sizes=(np.asarray(metadata["maximum"]) - metadata["origin"]) / (dimensions - 1),
        cells=dimensions - 1,
        properties=properties,
        cell_properties={
            "geological_unit": Categorical(unit_ids + 1, ["Air / outside", *names], colours),
            "unit_id": unit_ids,
            "fault_block_id": np.asarray(grid.cell_data["fault_block_id"], dtype=np.uint32),
        },
    )
    base = NAMESPACE + "/" + zone
    groups = [
        (base, zone, NAMESPACE),
        (base + "/contacts", "Geological contacts and constraints", base),
        (base + "/faults", "Faults and constraints", base),
    ]
    objects = [
        {
            "id": base + "/block",
            "name": "Geological block model",
            "parent": base,
            "object": block,
            "kind": "BlockModel",
            "colour_property": "geological_unit",
            "visible": False,
            "count": int(np.prod(dimensions - 1)),
            "source": str(directory / "implicit_fields.vts"),
        }
    ]
    inventory = pd.read_csv(directory / "surface_inventory.csv")
    constraints_directory.mkdir(parents=True, exist_ok=True)
    for record in inventory.itertuples():
        is_fault = record.surface.startswith("fault_")
        formation = record.surface[6:] if is_fault else record.surface[5:]
        group = base + ("/faults/" if is_fault else "/contacts/") + formation
        groups.append(
            (group, formation.replace("_", " "), base + ("/faults" if is_fault else "/contacts"))
        )
        colour = (65, 65, 65) if is_fault else rgb(example.COLOURS[formation])
        if isinstance(record.file, str) and record.file:
            path = directory / record.file
            mesh = pv.read(path)
            objects.append(
                {
                    "id": group + "/surface",
                    "name": "Fault surface" if is_fault else "Basal contact surface",
                    "parent": group,
                    "object": Surface(mesh.points, mesh.faces.reshape(-1, 4)[:, 1:]),
                    "kind": "Surface",
                    "colour": colour,
                    "opacity": 0.45 if is_fault else 0.7,
                    "count": mesh.n_cells,
                    "source": str(path),
                }
            )
        for source, orientation in ((contacts, False), (orientations, True)):
            rows = source.loc[source.formation == formation].copy()
            if rows.empty:
                continue
            positions = rows[example.XYZ].to_numpy(dtype=float)
            if not np.isfinite(positions).all():
                raise ValueError(f"Nonfinite input coordinates for {zone}/{formation}")
            inside = ((positions >= inputs.origin) & (positions <= inputs.maximum)).all(axis=1)
            props = {
                "source_row": rows.index.to_numpy(dtype=np.int64),
                "inside_model_domain": inside.astype(np.uint8),
                "formation": categorical(rows.formation, Categorical),
            }
            if orientation:
                props.update(
                    {
                        "source_section": categorical(rows["name"], Categorical),
                        "polarity": rows.polarity.to_numpy(dtype=float),
                        "dip_is_apparent": np.full(len(rows), not is_fault, dtype=np.uint8),
                    }
                )
                obj = Vectors(
                    vertices=positions,
                    # The source uses 360 degrees for north; GeoViewer's
                    # equivalent orientation convention uses [0, 360).
                    orientation=(rows.azimuth.to_numpy() % 360.0, rows.dip.to_numpy()),
                    properties=props,
                )
                kind, suffix, name = (
                    "Vectors",
                    "orientations",
                    "Fault dip constraints" if is_fault else "Section orientation constraints",
                )
            else:
                props["contact_value"] = np.zeros(len(rows))
                obj = Points(vertices=positions, properties=props)
                kind, suffix, name = (
                    "Points",
                    "contact-points",
                    "Fault trace constraints" if is_fault else "Contact point constraints",
                )
            path = constraints_directory / f"{record.surface}_{suffix}.vtp"
            cloud = pv.PolyData(positions)
            cloud.point_data["source_row"] = rows.index.to_numpy(dtype=np.int64)
            cloud.point_data["inside_model_domain"] = inside.astype(np.uint8)
            if orientation:
                cloud.point_data["dip"] = rows.dip.to_numpy()
                cloud.point_data["dip_direction"] = rows.azimuth.to_numpy()
                cloud.point_data["polarity"] = rows.polarity.to_numpy()
                cloud.point_data["pole"] = (
                    example.pole(rows.dip.to_numpy(), rows.azimuth.to_numpy())
                    * rows.polarity.to_numpy()[:, None]
                )
            cloud.field_data["crs"] = ["EPSG:32614"]
            cloud.field_data["formation"] = [formation]
            cloud.field_data["coordinates"] = [
                "original present-day coordinates, before restoration"
            ]
            cloud.save(path)
            objects.append(
                {
                    "id": group + "/" + suffix,
                    "name": f"{name} ({len(rows)})",
                    "parent": group,
                    "object": obj,
                    "kind": kind,
                    "colour": colour if orientation else (20, 20, 20),
                    "count": len(rows),
                    "source": str(path),
                }
            )
    picks = pd.read_csv(directory / "fault_displacement_picks.csv")
    for unit in example.ZONES[zone][0]:
        rows = picks.loc[(picks.unit == unit) & (picks.status == "paired_cutoffs")]
        if rows.empty:
            continue
        negative = rows[["negative_cutoff_" + axis for axis in example.XYZ]].to_numpy()
        positive = rows[["positive_cutoff_" + axis for axis in example.XYZ]].to_numpy()
        positions = np.stack([negative, positive], axis=1).reshape(-1, 3)
        segments = np.arange(len(positions)).reshape(-1, 2)
        obj = Lines(
            vertices=positions,
            segments=segments,
            properties={},
            cell_properties={
                "fault": categorical(rows.fault, Categorical),
                "source_section": categorical(rows.section, Categorical),
                "inferred_slip_m": rows.slip_m.to_numpy(),
                "inferred_throw_m": rows.throw_m.to_numpy(),
            },
        )
        objects.append(
            {
                "id": base + "/contacts/" + unit + "/displacement-cutoffs",
                "name": f"Paired displacement cutoffs ({len(rows)})",
                "parent": base + "/contacts/" + unit,
                "object": obj,
                "kind": "Lines",
                "colour": (235, 70, 50),
                "count": len(rows),
                "visible": False,
                "source": str(directory / "fault_displacement_picks.csv"),
            }
        )
    return {
        "zone": zone,
        "groups": groups,
        "objects": objects,
        "units": names,
        "directory": str(directory),
        "source_contacts": len(contacts),
        "source_orientations": len(orientations),
    }


def upload(cases: list[dict[str, Any]], output: Path) -> None:
    """Add the prepared hierarchy and verify it through a fresh viewer connection."""
    from loop_link import Viewer, ViewerRefusedError
    from loop_link.commands import run_command
    from loop_link.tool import ToolConnection

    if not os.environ.get("GEOVIEWER_TOKEN"):
        raise RuntimeError(
            "Set GEOVIEWER_TOKEN for this process; the uploader does not save tokens"
        )
    tool = ToolConnection(timeout=60)
    manifest = []
    with Viewer(crs="EPSG:32614", origin=(500000, 2180000, 0), timeout=60) as viewer:
        original_ids = {
            entry.id
            for entry in viewer.inventory()
            if entry.id != NAMESPACE and not entry.id.startswith(NAMESPACE + "/")
        }

        def command(name: str, arguments: dict[str, Any]) -> Mapping[str, Any]:
            return run_command(tool, name, arguments, timeout=60)

        try:
            # The basin spans over 100 km from the existing scene origin.
            # GeoViewer validates GPU precision at the scene's display
            # tolerance; 1 cm admits these positions without moving them.
            command("view.set_position_tolerance", {"tolerance": "1cm"})
            viewer.send_group(NAMESPACE, "Mexico Basin | LoopStructural")
            viewer.flush(0.2)
            for case in cases:
                zone = case["zone"]
                for object_id, name, parent in case["groups"]:
                    viewer.send_group(object_id, name, parent)
                viewer.flush(0.2)
                command(
                    "object.set_visible",
                    {"id": NAMESPACE + "/" + zone, "visible": zone == "North_2"},
                )
                for entry in case["objects"]:
                    object_id = entry["id"]
                    viewer.send(
                        entry["object"], id=object_id, name=entry["name"], parent=entry["parent"]
                    )
                    try:
                        viewer.flush(0.08)
                    except ViewerRefusedError as error:
                        print(
                            json.dumps(
                                {
                                    "refusals": [
                                        {"id": r.object_id, "code": r.code, "message": r.message}
                                        for r in error.refusals
                                    ]
                                }
                            ),
                            flush=True,
                        )
                        raise
                    if "colour_property" in entry:
                        viewer.set_colour_property(object_id, entry["colour_property"])
                        viewer.filter_values(
                            object_id,
                            entry["colour_property"],
                            list(range(1, len(case["units"]) + 1)),
                            timeout=60,
                        )
                    else:
                        viewer.set_object_colour(object_id, entry["colour"])
                    if "opacity" in entry:
                        command(
                            "object.set_opacity", {"id": object_id, "opacity": entry["opacity"]}
                        )
                    if entry["kind"] == "Points":
                        command("object.set_point_size", {"id": object_id, "size": 4})
                    if entry["kind"] == "Vectors":
                        command(
                            "glyph.set_glyph",
                            {"object": object_id, "group": "orientation", "glyph": "disc"},
                        )
                        command(
                            "glyph.set_size",
                            {"object": object_id, "group": "orientation", "text": "250"},
                        )
                    if not entry.get("visible", True):
                        command("object.set_visible", {"id": object_id, "visible": False})
                    manifest.append({key: value for key, value in entry.items() if key != "object"})
                viewer.flush(0.5)
                print(
                    json.dumps(
                        {
                            "uploaded": zone,
                            "groups": len(case["groups"]),
                            "objects": len(case["objects"]),
                        }
                    ),
                    flush=True,
                )
                (output / "upload_manifest.json").write_text(
                    json.dumps(manifest, indent=2), encoding="utf-8"
                )
            command("view.standard", {"view": "down", "zoom_to_all": False})
            command(
                "object.zoom_to",
                {
                    "ids": [
                        entry["id"]
                        for entry in manifest
                        if entry["kind"] == "Surface"
                        and entry["id"].startswith(NAMESPACE + "/North_2/")
                    ]
                },
            )
            viewer.flush(1.0)
        finally:
            tool.close()
    # Inventory read on a new data connection is returned by GeoViewer, rather
    # than the sending client's optimistic local inventory.
    with Viewer(timeout=60) as verify:
        inventory = {entry.id: entry for entry in verify.inventory()}
        missing = [entry["id"] for entry in manifest if entry["id"] not in inventory]
        lost_existing = sorted(original_ids - set(inventory))
        if missing or lost_existing:
            raise RuntimeError(
                f"Viewer verification failed: {len(missing)} missing additions; {len(lost_existing)} previous objects missing"
            )
        counts = {}
        for entry in manifest:
            expected_type = {"Vectors": "Points", "Lines": "Curve"}.get(
                entry["kind"], entry["kind"]
            )
            if inventory[entry["id"]].object_type != expected_type:
                raise RuntimeError(f"Viewer type differs for {entry['id']}")
            counts[entry["kind"]] = counts.get(entry["kind"], 0) + 1
        report = {
            "verified": True,
            "root_group": NAMESPACE,
            "cases": [case["zone"] for case in cases],
            "object_counts": counts,
            "preserved_previous_objects": len(original_ids),
            "source_crs": "EPSG:32614",
            "display_position_tolerance": "1cm",
            "viewer_crs": verify.scene_crs,
            "scene_origin": verify.scene_origin,
            "constraint_coordinates": "original present-day coordinates before restoration",
            "initial_visible_case": "North_2",
            "initial_hidden_objects": "other cases, block models and displacement cutoff lines; toggle them in the object tree",
        }
        (output / "verification.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report), flush=True)


def main() -> None:
    """Prepare and optionally upload the complete suite with no embedded credentials."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--loop-link-source", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "validation/mexico_basin_geoviewer")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.loop_link_source:
        sys.path.insert(0, str(args.loop_link_source))
    example = load_example()
    args.output.mkdir(parents=True, exist_ok=True)
    cases = []
    for zone in example.ZONES:
        directory = ROOT / "validation/mexico_basin_suite" / zone
        if zone == "North_2" and (ROOT / "validation/mexico_basin/North_2/model.json").exists():
            directory = ROOT / "validation/mexico_basin/North_2"
        cases.append(objects_for_zone(example, zone, directory, args.output / "constraints" / zone))
        print(json.dumps({"prepared": zone, "objects": len(cases[-1]["objects"])}), flush=True)
    if not args.dry_run:
        upload(cases, args.output)


if __name__ == "__main__":
    main()
