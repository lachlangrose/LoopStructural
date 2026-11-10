---
name: build-model
description: "Use this skill to build a LoopStructural GeologicalModel from CSV tables of contacts, orientations and a stratigraphic order, then plot a first section."
requires: LoopStructural>=1.11,<2
---

# Build a model from CSV tables

## When to use

Use this skill when the user has CSV tables of geological data and wants a
first 3D model. The tables hold contacts, orientations and a stratigraphic
order. The result is a `GeologicalModel` and a first cross section plot.

Do not use this skill to add faults or folds. Build the base model first.

## Input tables

The contacts table has these columns.

- `X`, `Y`, `Z`: the position of the point.
- `feature_name`: the name of the surface that the point belongs to.
- `val`: the scalar value of the surface at the point.

The orientations table has these columns.

- `X`, `Y`, `Z`: the position of the measurement.
- `feature_name`: the name of the surface that the measurement belongs to.
- Either `gx`, `gy`, `gz` (the gradient vector), or `strike` and `dip`.

Use the same `feature_name` text in both tables. Use one `feature_name` for
each stratigraphic group. A group is a set of units that share one surface
sequence.

Write the stratigraphic order as a list of unit names. The oldest unit is
first. Ask the user if the order is not known.

## Steps

### 1. Load the CSV files

```python
import pandas as pd

contacts = pd.read_csv("contacts.csv")
orientations = pd.read_csv("orientations.csv")
data = pd.concat([contacts, orientations], ignore_index=True)
print(data.head())
```

### 2. Make the model with a bounding box from the data

The `GeologicalModel` needs two arrays: the lower corner and the upper
corner of the model box. Take them from the data. Add a small buffer.

```python
import numpy as np
from LoopStructural import GeologicalModel

xyz = data[["X", "Y", "Z"]].to_numpy()
buffer = 0.1 * (xyz.max(axis=0) - xyz.min(axis=0))
origin = xyz.min(axis=0) - buffer
maximum = xyz.max(axis=0) + buffer
model = GeologicalModel(origin, maximum)
```

### 3. Give the model the data

```python
model.data = data
```

### 4. Add the foliations in stratigraphic order

Call `create_and_add_foliation` once for each group. Use the `feature_name`
of the group. Start with the oldest group.

```python
model.create_and_add_foliation("strati", nelements=1e4)
```

Then add the units to the stratigraphic column. Start from an empty column.
Give each unit a thickness. Use `np.inf` for the last unit.

```python
model.stratigraphic_column.clear(basement=False)
unit_names = ["unit_a", "unit_b", "unit_c"]
thicknesses = [60.0, 190.0, np.inf]
for i, name in enumerate(unit_names):
    model.stratigraphic_column.add_unit(name, thickness=thicknesses[i], id=i)
model.stratigraphic_column.group_mapping["Group_0"] = "strati"
```

The name `Group_0` is the first group. Map it to the `feature_name` of the
foliation. For more groups, use `Group_1` and the next name.

### 5. Update the model

```python
model.update()
```

### 6. Plot a first section

Evaluate the foliation on a grid in a vertical plane. Plot it with
matplotlib. The plane has a constant Y value at the middle of the box.

```python
import matplotlib.pyplot as plt

nx, nz = 100, 60
x = np.linspace(origin[0], maximum[0], nx)
z = np.linspace(origin[2], maximum[2], nz)
xx, zz = np.meshgrid(x, z)
yy = np.full_like(xx, 0.5 * (origin[1] + maximum[1]))
points = np.column_stack([xx.ravel(), yy.ravel(), zz.ravel()])
values = model.evaluate_feature_value("strati", points, scale=False)

fig, ax = plt.subplots()
image = ax.contourf(xx, zz, values.reshape(nz, nx), levels=20, cmap="viridis")
fig.colorbar(image, ax=ax, label="strati")
ax.set_xlabel("X")
ax.set_ylabel("Z")
ax.set_aspect("equal")
fig.savefig("first_section.png", dpi=150)
```

Show the plot to the user. Say which plane the section uses.

## Common errors

- Missing column. The model data needs `X`, `Y`, `Z` and `feature_name`.
  Check the column names with `data.columns`.
- A `feature_name` in the data does not match the name that you pass to
  `create_and_add_foliation`. The model then finds no data. Compare the
  names with `data["feature_name"].unique()`.
- The foliation has no `val` data. The interpolation needs at least two
  contact values or one value and one orientation. Check the data.
- An orientation uses a wrong unit. `strike` and `dip` are in degrees.
  `gx`, `gy`, `gz` is a vector, not an angle.
- The points are far from zero, for example UTM coordinates. Keep the
  values in the same coordinate system in all tables. Use `scale=False`
  when you evaluate the model at real coordinates, as in the section above.
- The section shows noise. The data are too few or conflict. Reduce
  `nelements`, or check that the order of `val` agrees with the order of
  the units.
- `set_model_data` is deprecated. Assign `model.data` instead.
