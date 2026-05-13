"""Build an example model with two configured stratigraphic series."""

from __future__ import annotations

import numpy as np

from loop_common.observations import PointSet
from loop_engine.core.model import Model
from loop_model.manager import GeologicalSchema


def _square_points(x0: float, y0: float, z: float) -> np.ndarray:
    return np.array(
        [
            [x0, y0, z],
            [x0 + 0.2, y0, z],
            [x0, y0 + 0.2, z],
            [x0 + 0.2, y0 + 0.2, z],
        ],
        dtype=float,
    )


def build_model() -> Model:
    schema = GeologicalSchema(name="TwoSeriesExample")
    schema.initialize_project()

    # Series A (base at 0.0) uses metadata["thickness"].
    a_older = schema.add_unit(
        name="A_Older",
        metadata={"thickness": 10.0},
        basal_contacts=[PointSet(name="a_old_basal", coords=_square_points(0.1, 0.1, 0.0))],
    )
    a_younger = schema.add_unit(
        name="A_Younger",
        metadata={"thickness": 6.0},
        basal_contacts=[PointSet(name="a_young_basal", coords=_square_points(0.1, 0.1, 1.0))],
    )

    # Series B (base at 100.0) uses metadata["series_thick"] override.
    b_older = schema.add_unit(
        name="B_Older",
        metadata={"series_thick": 4.0},
        basal_contacts=[PointSet(name="b_old_basal", coords=_square_points(0.6, 0.6, 2.0))],
    )
    b_younger = schema.add_unit(
        name="B_Younger",
        metadata={"series_thick": 2.5},
        basal_contacts=[PointSet(name="b_young_basal", coords=_square_points(0.6, 0.6, 3.0))],
    )

    schema.add_conformable_overlies_relation(master_uuid=a_younger.uuid, slave_uuid=a_older.uuid)
    schema.add_conformable_overlies_relation(master_uuid=b_younger.uuid, slave_uuid=b_older.uuid)

    strategy = {
        "mode": "shared_scalar_field",
        "series_config": {
            "default": {
                "series_band_mode": "cumulative_thickness",
                "series_thickness_source": "unit_metadata",
                "series_thickness_key": "thickness",
                "series_thickness_fallback": 1.0,
            },
            "groups": [
                {
                    "units": ["A_Older", "A_Younger"],
                    "series_base_isovalue": 0.0,
                },
                {
                    "units": ["B_Older", "B_Younger"],
                    "series_base_isovalue": 100.0,
                    "series_thickness_key": "series_thick",
                },
            ],
        },
    }

    return Model(schema=schema, interpolatortype="FDI", nelements=200, interpolation_strategy=strategy)


def main() -> None:
    model = build_model()

    # Inspect interpreted scalar bands before solve.
    tasks = model._compile_tasks()
    print("Interpreted stratigraphic bands:")
    for task in tasks:
        info = task.interpretation
        if "basal_isovalue" not in info:
            continue
        feature_name = model.schema.features[task.id].name
        print(
            f"  {feature_name:9s} -> basal={info['basal_isovalue']:.2f}, "
            f"top={info['top_isovalue']:.2f}, series={info['series_key']}"
        )

    state = model.solve()
    print(f"Solved features: {len(state.results)}")


if __name__ == "__main__":
    main()
