"""Training isolation, source validation and expert constraint checks."""

import json
from pathlib import Path

import numpy as np
import pytest

from docs.experiments.fault_kinematic_inference.experiment.constraints import compile_constraints
from docs.experiments.fault_kinematic_inference.experiment.data import load_training, validate_table
from docs.experiments.fault_kinematic_inference.experiment.schema import BASE, load_config


def configuration(case="E0"):
    return load_config(BASE / "configs" / f"simple_{case.lower()}.json")


def test_training_allowlist(monkeypatch):
    original_read, original_open = Path.read_bytes, Path.open
    accessed = []

    def checked_open(path, *args, **kwargs):
        accessed.append(str(path))
        assert "truth" not in path.parts and not path.name.endswith("_test.csv")
        assert path.name not in ("contacts.csv", "bedding.csv", "contact_traces.geojson")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", checked_open)
    data = load_training(configuration(), 0)
    assert len(data.contacts) > 0 and accessed
    assert "val" not in data.constraints
    assert all("truth" not in p and "_test" not in p for p in data.hashes)
    assert original_read  # Keep byte access covered by the patched open method.


def test_direction_norm_is_not_magnitude():
    config = configuration("E1")
    card = json.loads((BASE / "datasets" / config["dataset"] / "constraints.json").read_text())
    first = compile_constraints(config, card)
    card["E1"]["slip_direction"] = (np.array(card["E1"]["slip_direction"]) * 123).tolist()
    second = compile_constraints(config, card)
    np.testing.assert_allclose(first["fixed"]["direction_unit"], second["fixed"]["direction_unit"])
    assert first["free_parameters"] == ["D_m"]
    assert "D_m" not in first["fixed"]
    card["E1"]["slip_direction"] = [1, 0, 0]
    with pytest.raises(ValueError, match="outside"):
        compile_constraints(config, card)


def test_invalid_units_missing_normals_bounds_and_wall():
    data = load_training(configuration(), 0)
    for column, value in [("X", np.nan), ("Y", 1e7), ("wall", 0), ("position_sigma_m", -1)]:
        table = data.contacts.copy()
        table.loc[0, column] = value
        with pytest.raises(ValueError):
            validate_table(table, "contacts", data.bounds)
    table = data.bedding.copy()
    table.loc[0, "nx"] = 50
    with pytest.raises(ValueError, match="unit"):
        validate_table(table, "bedding", data.bounds)


def test_source_hash_change_is_rejected(tmp_path):
    import shutil

    config = configuration()
    source = BASE / "datasets" / config["dataset"]
    # Copy only allowed inputs. The loader cannot rely on test/truth files existing.
    names = [
        "manifest.json",
        "constraints.json",
        "faults.geojson",
        "dem.tif",
        "SHA256SUMS.json",
        "splits/fold_0/mask.json",
        "splits/fold_0/contacts_train.csv",
        "splits/fold_0/bedding_train.csv",
    ]
    for name in names:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / name, target)
    assert len(load_training(config, 0, tmp_path).contacts) > 0
    with (tmp_path / names[-1]).open("a") as stream:
        stream.write("\n")
    with pytest.raises(ValueError, match="hash mismatch"):
        load_training(config, 0, tmp_path)
