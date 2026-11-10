---
name: inspect-model
description: "Inspect a saved model or a model script: list the features, show their data, find common problems."
requires: LoopStructural>=1.11,<2
---

# Inspect a LoopStructural model

## When to use

Use this skill when the user has a `GeologicalModel` and wants to know what it holds.
The model can be a saved file or a Python script that builds the model.
Use it to list the features, to show the data of each feature, and to find common problems.
Do not use it to build a new model.

## Load a model or run a model script

Choose the source that the user gave.

### A saved model file

Load a file with `GeologicalModel.from_file`.
The loader uses `dill`. A file from an unknown source can run code on this machine.
Load only a file that the user made or trusts.
Pass `allow_pickle=False` to refuse a pickle file.

```python
from LoopStructural import GeologicalModel

model = GeologicalModel.from_file("model.pkl")
print(model)
```

### A recipe file

A recipe is a JSON description of a model.
It is safe to load, because it is not a pickle file.
Use `GeologicalModel.load_recipe`.

```python
from LoopStructural import GeologicalModel

model = GeologicalModel.load_recipe("model_recipe.json")
print(model)
```

### A model script

Run the script of the user in a Python process.
Then use the variable that holds the model.
Ask the user for the name of this variable if it is not clear.
Do not edit the script.

```python
import runpy

namespace = runpy.run_path("build_model.py")
model = namespace["model"]
print(model)
```

## List the features and their data

Print the number of features first.
`str(model)` gives the count.

```python
print(model)
print(list(model.feature_names()))
print(model.fault_names())
```

Get one feature with its name.
The name must be in the model.

```python
name = "strati"
if name in model:
    feature = model[name]
    print(feature.name, feature.type)
```

Show the data of one feature.
`data_for_feature` returns a pandas `DataFrame`.

```python
data = model.data_for_feature(name)
print(len(data))
print(data.head())
```

Show the data of all features in one table.

```python
for feature_name in model.feature_names():
    rows = model.data_for_feature(feature_name)
    print(feature_name, len(rows))
```

Show the bounding box of the model.

```python
box = model.bounding_box
print(box.origin)
print(box.maximum)
print(box.nsteps)
```

## Checks for common problems

Run each check. Collect the results. Do not stop at the first problem.

### Missing data

A feature with no data rows cannot be interpolated well.
Look for the feature names that have zero rows.

```python
problems = []
for feature_name in model.feature_names():
    rows = model.data_for_feature(feature_name)
    if len(rows) == 0:
        problems.append(f"{feature_name}: no data rows")
```

Check the columns of the table.
The table must have a `feature_name` column.
It usually has the coordinate columns `X`, `Y` and `Z`.

```python
columns = list(model.data.columns)
for column in ["feature_name", "X", "Y", "Z"]:
    if column not in columns:
        problems.append(f"data table has no column {column}")
```

Look for empty cells in the coordinates.

```python
coordinates = model.data[["X", "Y", "Z"]]
if coordinates.isna().any().any():
    problems.append("the data has missing coordinates")
```

### Bad bounds

The maximum of the bounding box must be larger than the origin on each axis.
Look at the `valid` property of the box.

```python
import numpy as np

box = model.bounding_box
if not box.valid:
    problems.append("the bounding box is not valid")
if np.any(box.maximum <= box.origin):
    problems.append("the bounding box has a zero or negative size")
```

Check that the data lies inside the bounding box.
Data outside the box does not help the interpolation.

```python
inside = (
    (model.data["X"] >= box.origin[0])
    & (model.data["X"] <= box.maximum[0])
    & (model.data["Y"] >= box.origin[1])
    & (model.data["Y"] <= box.maximum[1])
    & (model.data["Z"] >= box.origin[2])
    & (model.data["Z"] <= box.maximum[2])
)
outside = int((~inside).sum())
if outside > 0:
    problems.append(f"{outside} data rows are outside the bounding box")
```

### Empty features

A feature is empty if it gives no finite value.
Evaluate the feature at the centre of the box.
Use `evaluate_feature_value`.

```python
centre = np.array([(box.origin + box.maximum) / 2.0])
for feature_name in model.feature_names():
    values = model.evaluate_feature_value(feature_name, centre)
    if not np.all(np.isfinite(values)):
        problems.append(f"{feature_name}: no finite value at the centre")
```

A feature can also have an interpolator that did not solve.
Check `is_valid` on features that have an interpolator.
Some feature types do not have this method.

```python
for feature_name in model.feature_names():
    feature = model[feature_name]
    check = getattr(feature, "is_valid", None)
    if check is not None and not check():
        problems.append(f"{feature_name}: the interpolator is not valid")
```

### Stratigraphic column

If the model has a stratigraphic column, print it.
Check that each unit has a feature that belongs to it.

```python
column = model.stratigraphic_column
print(column)
```

## How to report the result

Write the report in plain, short sentences.
Use this order.

1. State the source: the file or the script, and how the model was loaded.
2. State the number of features, and list their names. Mark the faults.
3. Give one line for each feature: the name, and the number of data rows.
4. State the bounding box: the origin, the maximum and the number of steps.
5. List each problem that the checks found. Put the feature name first.
6. If the checks found no problem, say so. Do not say that the model is correct.

Say what you did not check.
The checks do not test whether the model is geologically correct.
Suggest one next step for each problem.
For example, tell the user to add data for a feature with no rows.

Do not change the model or the files of the user during an inspection.
Do not save the model unless the user asks.
