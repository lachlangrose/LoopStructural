---
name: map2loop-prepare
description: "Use map2loop to turn map data into the contact and orientation tables that the build-model skill needs."
requires: map2loop>=3.5,<4
---

# Prepare map data with map2loop

## When to use

Use this skill when the user has geological map data and no contact or orientation tables.
Map data means a geology polygon layer, a structure point layer and a DEM.
Use the `build-model` skill when the user already has the tables.

Do not write a `map2loop` name from memory.
The installed `map2loop` version is the source of truth.
Read its documentation and its source for the exact arguments.

## Map data inputs

The `map2loop` `Project` class reads these inputs.

| Input | `Project` argument | Required |
| --- | --- | --- |
| Geology polygons | `geology_filename` | yes |
| Structure points (dip and dip direction) | `structure_filename` | yes |
| Digital elevation model | `dtm_filename` | yes |
| Fault lines | `fault_filename` | no |
| Fold axial traces | `fold_filename` | no |
| Column names of the layers | `config_filename` or `config_dictionary` | yes, if names are not the default |
| Working projection | `working_projection` (for example `"EPSG:28354"`) | yes |
| Model extent | `bounding_box` | yes |

The `bounding_box` is a dictionary with the keys `minx`, `maxx`, `miny`, `maxy`, `base` and `top`.
Give it in the units of the working projection.
Ask the user for the projection and the extent.
Do not guess them.

The configuration tells `map2loop` which column of each layer holds the unit name, the dip and the dip direction.
Ask the user for the column names.
Read the `map2loop` documentation for the format of the configuration.

## Steps

### 1. Check that map2loop is installed

`map2loop` needs GDAL.
If the import fails, tell the user to install `map2loop` with conda.
Do not try to build GDAL.

```python
import map2loop
from map2loop.project import Project
from map2loop.m2l_enums import Datatype
```

### 2. Make the project

The `Project` reads, reprojects and clips the data when it is made.
Use the file names and the extent of the user.

```python
bounding_box = {
    "minx": 250000.0,
    "maxx": 340000.0,
    "miny": 6400000.0,
    "maxy": 6460000.0,
    "base": -3200.0,
    "top": 1200.0,
}

proj = Project(
    working_projection="EPSG:28354",
    bounding_box=bounding_box,
    geology_filename="geology.shp",
    structure_filename="structure.shp",
    dtm_filename="dem.tif",
    fault_filename="faults.shp",
    config_dictionary={},
    loop_project_filename="map2loop_output.loop3d",
    overwrite_loopprojectfile=True,
)
```

The numbers and file names above are examples.
Replace all of them with the values of the user.
Pass the column names in `config_dictionary` or in `config_filename`.
If the project has no fault layer, remove `fault_filename`.

### 3. Run the processing

`run_all` extracts the contacts, finds the stratigraphic order, samples the map data and writes a `.loop3d` file.

```python
proj.run_all()
```

To set the stratigraphic order yourself, pass a list of unit names from the youngest to the oldest.
The argument is `user_defined_stratigraphic_column`.
Ask the user for this list when the unit hints in the data are poor.

### 4. Read the outputs

After `run_all`, the project holds these data.

| Attribute | Content |
| --- | --- |
| `proj.map_data.sampled_contacts` | Points on the basal contacts, with `ID`, `X`, `Y`, `Z` and `featureId` |
| `proj.contact_extractor.basal_contacts` | The basal contact lines, with `ID` and `basal_unit` |
| `proj.structure_samples` | Dip points, with `X`, `Y`, `Z`, `layerID`, `DIPDIR`, `DIP` and `OVERTURNED` |
| `proj.stratigraphic_column.column` | The unit names in stratigraphic order, youngest first |
| `proj.stratigraphic_column.stratigraphicUnits` | The unit table, with `name` and the thickness columns |
| `proj.fault_samples` | Points on the fault traces |
| `proj.fault_orientations` | Fault dip and dip direction |

Check the first rows of each table before you convert it.
Column names can change between `map2loop` versions.

### 5. Make the contact table

The `build-model` skill needs these columns: `X`, `Y`, `Z`, `feature_name` and `val`.
One foliation is one stratigraphic group.
Ask the user for the name of the group.
The default is `strati`, with all units in one group.
Use this one name in `feature_name` for all contact points.
Do not use a unit name in `feature_name`.

The `val` column is the value of the scalar field at the point.
It is the height of the contact above the base of the group.
This height is the cumulative thickness of the units below the contact.
The lowest contact has the smallest `val`.
All points of one contact surface have the same `val`.

The `proj.stratigraphic_column.column` list runs from the youngest unit to the oldest unit.
Add the thicknesses from the oldest unit up.
The `val` of the base of a unit is the sum of the thicknesses of all older units.
The base of the oldest unit has `val` 0.0.

`run_all` fills the thickness data.
It adds the columns `<label>_median`, `<label>_mean` and `<label>_stddev` to `proj.stratigraphic_column.stratigraphicUnits`.
The label is the result of `proj.get_active_thickness()`.
A value of -1 or an empty value means that `map2loop` found no thickness for that unit.
Show the thicknesses to the user and ask the user to confirm them.
Replace each bad value with a value from the user.

```python
import numpy as np
import pandas as pd

column = list(proj.stratigraphic_column.column)  # youngest first
units = proj.stratigraphic_column.stratigraphicUnits
label = proj.get_active_thickness()
thickness = dict(zip(units["name"], units[f"{label}_median"]))
thickness = {name: thickness.get(name) for name in column}
print(thickness)
```

If a value is missing or not above 0, the user gives it.
Then fill the dictionary by hand, in model units.
The unit names are examples.

```python
thickness = {"unit A": 250.0, "unit B": 400.0, "unit C": 120.0}
```

Make the `val` dictionary from the thicknesses.
Also make the table of units for the `build-model` skill.

```python
val = {}
total = 0.0
for name in reversed(column):  # oldest first
    val[name] = total
    total += float(thickness[name])

unit_table = pd.DataFrame(
    {
        "unit": column,
        "thickness": [float(thickness[name]) for name in column],
        "val": [val[name] for name in column],
    }
)
print(unit_table)
unit_table.to_csv("units.csv", index=False)
```

Now make the contact table.
The `ID` column of the contact points is the number of the unit.
The `basal_unit` column of the basal contact lines gives the unit name for each `ID`.
The type of `ID` can differ between the two tables.
Convert both to numbers before you map.

```python
group_name = "strati"

contact_points = proj.map_data.sampled_contacts
basal_lines = proj.contact_extractor.basal_contacts
names = dict(
    zip(pd.to_numeric(basal_lines["ID"], errors="coerce"), basal_lines["basal_unit"])
)
point_ids = pd.to_numeric(contact_points["ID"], errors="coerce")
unit_of_point = point_ids.map(names)

contacts = pd.DataFrame(
    {
        "X": contact_points["X"],
        "Y": contact_points["Y"],
        "Z": contact_points["Z"],
        "feature_name": group_name,
        "unit": unit_of_point,
        "val": unit_of_point.map(val),
    }
)
contacts = contacts.dropna(subset=["X", "Y", "Z", "unit", "val"])
if contacts.empty:
    print(contact_points.head())
    print(basal_lines.head())
    raise SystemExit("No contact points have a unit name. Check the ID columns.")
contacts.drop(columns=["unit"]).to_csv("contacts.csv", index=False)
```

If the table is empty, stop.
Show the first rows of both input tables to the user.
A unit that is not in the stratigraphic column has no `val`.
`dropna` removes the points of such a unit.

### 6. Make the orientation table

The `build-model` skill accepts `strike` and `dip`.
The `map2loop` structure points hold a dip direction in `DIPDIR`.
The strike for the right-hand rule is the dip direction minus 90 degrees.
Use the same `group_name` in `feature_name` as in the contact table.
The orientation points have no `val`.

```python
points = proj.structure_samples
orientations = pd.DataFrame(
    {
        "X": points["X"],
        "Y": points["Y"],
        "Z": points["Z"],
        "feature_name": group_name,
        "strike": (points["DIPDIR"] - 90.0) % 360.0,
        "dip": points["DIP"],
    }
)
orientations = orientations.dropna()
orientations.to_csv("orientations.csv", index=False)
```

Check one measurement by hand.
A dip direction of 90 degrees must give a strike of 0 degrees.
Remove the points where `OVERTURNED` is true, or flip them, if the user has overturned beds.
If the user wants more than one group, ask for the group of each unit.
Then make one pair of tables for each group.

### 7. Check the tables

```python
print(contacts.groupby("feature_name").size())
print(orientations.groupby("feature_name").size())
print(contacts.groupby("val").size())
print(contacts.groupby("val")["Z"].agg(["min", "max"]))
print(contacts[["X", "Y", "Z"]].describe())
```

Check these points.

- The group name is the same in `contacts.csv` and `orientations.csv`.
- Each contact surface has one `val`.
  The `groupby("val")` output must show one row for each unit base.
- The `val` of the oldest unit is 0.0 and the `val` values rise toward the younger units.
- Each unit that you want to model has contact points.
- The `X`, `Y` and `Z` ranges are inside the `bounding_box`.
- The `Z` values are not empty.
  An empty `Z` means that the DEM does not cover the extent.

## Hand-over to build-model

Give the `build-model` skill these items.

- `contacts.csv` with `X`, `Y`, `Z`, `feature_name`, `val`.
- `orientations.csv` with `X`, `Y`, `Z`, `feature_name`, `strike`, `dip`.
- The group name.
  It must be the same in both CSV files.
  It must also be the name in the `create_and_add_foliation` call of `build-model`.
- `units.csv`, the table of units from the youngest to the oldest.
  It has the columns `unit`, `thickness` and `val`.
  The `build-model` skill uses it for its unit list.
  The thickness of a unit is the `val` of its top contact minus the `val` of its base contact.
  The oldest unit is the first unit in the model, and the youngest unit has no top contact.
- The `bounding_box`, converted to an origin and a maximum corner.
  The origin is `(minx, miny, base)`.
  The maximum is `(maxx, maxy, top)`.
- The stratigraphic order from `proj.stratigraphic_column.column`, youngest first.
- The working projection.

Tell the user that the faults are not in these tables.
Fault traces are in `proj.fault_samples`.
Use them only if the user asks for a fault in the model.

## Things to tell the user

- `map2loop` also writes a `.loop3d` file.
  This skill does not use it.
- `run_all` can take minutes on a large map.
- If `Project` raises an error for a missing input, read the message.
  It names the argument that is missing.
- The unit order comes from the data hints.
  Check it with the user before you build a model.
