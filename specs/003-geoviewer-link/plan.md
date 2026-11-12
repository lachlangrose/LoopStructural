# Implementation plan: Python link to GeoViewer

**Feature**: `003-geoviewer-link` | **Date**: 2026-10-29 | **Spec**: [spec.md](spec.md)

<!-- A plan says HOW. Write in ASD-STE100 Simplified Technical English. -->

## Open points

| Id | Question | Default if the user does not answer | Tasks that wait |
|---|---|---|---|
| OP1 | GeoViewer has no rotation for a BlockModel. A `StructuredGrid3DGeometry` with `rotation_xy` other than 0 cannot go there in its true position. | The adapter refuses it (FR-004) and names the GeoViewer gap. Open a GeoViewer spec for a rotated BlockModel. | none (refuse is the default) |
| OP2 | The protocol cannot set the active colour array in `scene.upsert`. The scene file has `colour.active`, but the wire format does not. | `GeoViewerView` runs `colour.set_active`, `colour.set_map` and `colour.set_range` on a tool session after the push (D6). Open a GeoViewer spec to add `colour` to `scene.upsert`. | none |
| OP3 | `StructuredGrid2DGeometry` has a 2D origin. GeoViewer needs a 3D origin for a `Grid2D`. | The adapter takes a keyword `z` (default 0.0). | T021, T024 |
| OP4 | The MCP SDK needs Python 3.10 or later. The constitution sets the lint target to Python 3.9. | The extra `mcp` needs Python 3.10. The base package stays at 3.9. The MCP module is not imported by `import loop_link`. | T060, T061 |
| OP6 | Story 7 needs GeoViewer to give the selection: a command `selection.get` and an event `selection.changed` (and click hits) on the tool connection. | Phase F waits. Write the GeoViewer spec (D9 lists what it must give). | T080 to T085 |
| OP5 | Until GeoViewer is in this repository, the protocol fixtures are a copy. | Copy `fixtures/protocol/expected/` of GeoViewer into `packages/loop_link/tests/fixtures/geoviewer/`. Write the GeoViewer commit in a `SOURCE.txt` file. | T010 |

The orchestrator starts a task with `Blocked by` only after the user
confirms the open point.

## Summary

Extend `packages/loop_link`. Do not start a new package. Keep it numpy-only.

1. Bring the GeoViewer messages to protocol 1.10, and add `Points`,
   `Grid2D`, `BlockModel`, `TetraMesh`, data arrays and property groups.
2. Add **adapters**: functions that change an object with the attributes of a
   `loop_common.geometry` type into a `scene.upsert` frame. They read
   attributes only. They do not import `loop_common` (FR-002).
3. Add **discovery** (`connect()`) from the GeoViewer instance files, the
   saved token and `GEOVIEWER_TOKEN`.
4. Add a **tool session** on `/tool`: commands, screenshot, pick.
5. Add `GeoViewerView` to `loopstructural_visualisation`, with the method
   names of `Loop3DView`.
6. Add an optional MCP server, `loop_link.mcp`.
7. Remove the import of pyvista at the top of `loop_common/geometry/_surface.py`.

## Technical context

- **Packages changed**
  - Changed: `packages/loop_link` (on the branch `feat/loop-geoviewer-client`;
    it is staged, not committed).
  - Changed: `packages/loopstructural_visualisation` (new class, new extra).
  - Changed: `packages/loop_common` (one import).
  - Changed: `.release-please-config.json` (the entry for `loop_link` is
    already in the working copy).
- **GeoViewer reference**: protocol 1.10, `docs/protocol.md` and
  `fixtures/protocol/expected/` of the GeoViewer repository, checked on
  2026-10-29.
- **New dependencies**
  - `loop_link`: none required. Optional extra `mcp = ["mcp"]`.
  - `loopstructural_visualisation`: optional extra
    `geoviewer = ["loop-link"]`.
- **No PIL in the base package.** A small PNG writer with `zlib` and
  `struct` (about 30 lines) makes the image for Jupyter and MCP (D5).
- **Python**: base 3.9 or later; the extra `mcp` 3.10 or later (OP4).

## Repo-fit check

| Rule (constitution) | How this plan obeys it |
|---|---|
| Work ships as independently testable, reversible stages | Phases A to E. Each phase has its own tests and can merge alone. |
| The public `GeologicalModel` API is a hard boundary | No change to it. `GeoViewerView` only reads features. |
| The QGIS plugin stays in a separate repository | The plugin uses `loop_link` from PyPI. `loop_link` stays numpy-only (FR-001). |
| Specs under `specs/NNN-name/` | This folder. |
| Release-please with per-package paths | `packages/loop_link` gets its own component, `loop-link`. |
| `pytest` and `ruff check` before merge | Each phase runs both. New code has numpy docstrings and type hints (`D`, `ANN`). |
| `ROADMAP.md` is the architecture reference | Add one entry for `loop_link` and `GeoViewerView` when phase D is done (T072). |

## Design

### D1. Package layout

```
packages/loop_link/src/loop_link/
  frame.py               # exists: binary frame codec
  websocket_client.py    # exists: stdlib WebSocket client
  link.py                # exists: Link and Session
  png.py                 # new: RGBA array -> PNG bytes (D5)
  geoviewer/
    __init__.py          # exports connect, GeoViewerLink, ToolSession, adapters
    protocol.py          # exists: extend to 1.10, all object types (D2)
    shapes.py            # new: typing.Protocol for each loop_common type (D3)
    adapters.py          # new: object -> scene.upsert frame (D3)
    discovery.py         # new: find the viewer and the token (D4)
    link.py              # exists: GeoViewerLink.push; add connect()
    tool.py              # new: ToolSession (D5)
  mcp/                   # new, extra "mcp" only (D7)
    __init__.py
    server.py
packages/loopstructural_visualisation/src/loopstructuralvisualisation/
  _geoviewer_view.py     # new: GeoViewerView (D6)
```

The layers do not change: `frame` and `link` know nothing about GeoViewer.
`geoviewer.protocol` knows the messages and nothing about `loop_common`.
`geoviewer.adapters` knows the attribute shapes. `GeoViewerView` knows
LoopStructural features.

### D2. Protocol messages (`geoviewer/protocol.py`)

- Set `PROTOCOL_VERSION` to `{'major': 1, 'minor': 10}`.
- Add a `DataArray` description and a function that makes the data entry and
  its buffer from a numpy array:

  | numpy kind | `data_type` | buffer |
  |---|---|---|
  | float (`f`) | `float` | `f32` |
  | signed or unsigned integer in the `i32` range | `integer` | `i32` |
  | bool | `boolean` | `u8` |
  | string or object of `str` | `text` | `u8` bytes + `u32` offsets |

  A `float` array keeps NaN (no-data). An integer outside the `i32` range is
  refused (FR-004). `referenced` arrays are out of scope for now.
- Add message functions, each with the checks of `docs/protocol.md`:
  `points_message`, `grid2d_message`, `blockmodel_message`,
  `tetramesh_message`, and extend `surface_message` with `data` and
  `property_groups`. Keep one internal function for the coordinate rule:
  subtract the origin in `f64`, then use `f32` if all values are within
  4000 m of the origin, else `f64` (this is the rule of `surface_message`
  now).
- Add `style_message` (`scene.style`) and `data_message` (`scene.data`).
- Each message function checks the array lengths, NaN and infinite
  coordinates, and index ranges, and raises `ProtocolError` with the object
  name (FR-004).

### D3. Adapters (`geoviewer/shapes.py`, `geoviewer/adapters.py`)

`shapes.py` defines one `typing.Protocol` for each type, with only the
attributes that the adapter reads. `adapters.to_message(obj, object_id,
origin, *, parent=None, name=None, **options)` selects the adapter by
attributes, in this order, and raises `TypeError` for an object that matches
none.

| `loop_common` type | Attributes read | GeoViewer object | Notes |
|---|---|---|---|
| `Surface` | `vertices`, `triangles`, `name`, `values`, `properties`, `cell_properties` | `Surface` | `values` is a vertex array named `values`. |
| `ValuePoints` | `locations`, `values`, `name`, `properties` | `Points` | `values` is a vertex array named `values`. |
| `VectorPoints` | `locations`, `vectors`, `name`, `properties` | `Points` + `orientation` group | D3.1 |
| `StructuredGrid2DGeometry` | `origin` (2), `nsteps`, `step_vector`, and keyword `z` | `Grid2D` | `cells = nsteps - 1`; `size = cells * step_vector`; `rotation = 0`; `dip = 0`; `origin = [x, y, z]` (OP3). |
| `StructuredGrid3DGeometry` | `origin`, `nsteps`, `step_vector`, `rotation_xy` | `BlockModel` | `cells = nsteps - 1`; `cell_sizes = step_vector`. Refuse if `rotation_xy` is not 0 (OP1). |
| `UnstructuredMeshGeometry` | `nodes`, `elements` | `TetraMesh` | Use `elements[:, :4]` (the P2 mesh has more columns). |

Properties of a grid come as a keyword `properties={'name': array}`. The
adapter decides the association from the length: the node count gives
`vertex`, the cell count gives `cell`, any other length is refused.

**Node order.** `loop_common` makes the nodes with
`meshgrid(..., indexing="ij")` and `flatten(order="F")`. The x index changes
fastest. This is the VTK order of GeoViewer. A test checks this (T022).

#### D3.1 Vectors to orientations

GeoViewer draws a disc for an `orientation` group with the members
`dip_direction`, `dip` and `polarity`. For each vector `v`:

- `n = v / |v|`. If `n_z < 0`, then `n = -n` and polarity is 0
  (overturned), else polarity is 1 (upright). A zero vector gives NaN for dip
  direction and dip, and polarity -1.
- `dip = degrees(arccos(n_z))`, from 0 to 90.
- `dip_direction = degrees(arctan2(n_x, n_y)) mod 360`, clockwise from north.
- The adapter also sends `|v|` as a float array named `magnitude`.

A keyword `kind='lineation'` sends a `lineation` group (`trend`, `plunge`)
instead, for a vector that is a line and not a plane normal.

### D4. Discovery (`geoviewer/discovery.py`)

- Settings folder: `%APPDATA%\geoviewer` on Windows, `$HOME/.geoviewer`
  elsewhere.
- Read each `instances/*.json`: `version`, `pid`, `port`, `kind`
  (`window` or `headless`), `started`, `focused`.
- Sort: `window` before `headless`, then the newest `focused`.
- For each one, open a TCP connection to `127.0.0.1:port` with a timeout of
  0.5 s. Use the first one that answers. Do not delete a stale file. It is the
  file of GeoViewer.
- Token: `GEOVIEWER_TOKEN` if it is not empty, else `token` from `link.json`.
  Never print or log the token.
- `connect(port=None, token=None)` returns a `GeoViewerLink`. A given argument
  wins over discovery.
- Errors: "No GeoViewer is running. Start GeoViewer." and "No saved token.
  In GeoViewer, open the link popup, click New random token, then Apply."

### D5. Tool session (`geoviewer/tool.py`, `png.py`)

- `GeoViewerLink.tools()` is a context manager. It opens a WebSocket on the
  path `/tool`, with an incoming limit of 300 MiB (the 16 MiB limit stays for
  the data path). A tool sends no `hello`.
- Each request has a `request` number. The session reads until the reply with
  the same number. It skips `command.progress` and can pass it to a callback.
- Methods:
  - `commands()` returns a list of `Command` (name, description,
    `input_schema`, `result_schema`, `needs_window`, `tool_available`). The
    reply field for the kind of viewer is `viewer` (not `kind`, as
    `docs/protocol.md` of GeoViewer says now).
  - `run(name, input=None, timeout=30)` returns the `result`. A
    `request.error` raises `ViewerError(code, message, field)` (FR-007).
  - `screenshot(width=None, height=None, camera=None)` returns a
    `Screenshot`: an RGBA `uint8` array of shape `(h, w, 4)`, with
    `_repr_png_()` for Jupyter and `to_png()` for files and MCP.
  - `pick_ray(origin, direction, max_hits=10)` and
    `pick_screen(x, y, max_hits=10)` return the list of hits.
- `png.py` writes an 8-bit RGBA PNG with `zlib` and `struct`. No filter (type
  0 on each row). A test reads it back with PIL when PIL is installed, and
  checks the byte layout when it is not.

Verified on 2026-10-29 against a real viewer: `commands.list` (78 commands),
`command.run` of `view.zoom_all`, `object.set_point_size` and
`colour.set_active` (input field `array`), and a 960 by 600 screenshot.

### D6. `GeoViewerView` (`loopstructural_visualisation`)

- It is not a subclass of `pv.Plotter`. It does not import pyvista.
- `GeoViewerView(model=None, link=None, group='loop')`. With no link it calls
  `connect()`.
- Methods with the same names and arguments as `Loop3DView`:
  `plot_surface`, `plot_scalar_field`, `plot_data`, `plot_model_surfaces`,
  `plot_block_model` and `plot_vector_field`. Each method gets the
  `loop_common` objects from the feature in the same way as `Loop3DView`
  (`feature.surfaces(...)`, `feature.get_data()`,
  `model.regular_grid(...)`), then calls the adapters.
- Arguments that only pyvista knows (`pyvista_kwargs`, `slicer`,
  `show_scalar_bar` and others) are accepted and ignored, with one warning for
  each name in each view (spec story 1, scenario 4).
- **Ids.** `<group>/<feature name>/<kind>[/<index>]`, for example
  `loop/fault1/surface/0`. A second call with the same id replaces the
  object (FR-009). The view keeps a `Group` for each feature.
- **One push for each call.** A call makes one data session (`push`) with
  `replace_prefix` set to the ids of that call. Then the old objects of the
  same call go away. The data session is short, so another client can connect
  between calls.
- **Colour and style (OP2).** After the push, if the call has `cmap`,
  `vmin`, `vmax`, `colour` or `opacity`, the view opens one tool session and
  runs `colour.set_active`, `colour.set_map`, `colour.set_range`,
  `object.set_colour` and `object.set_opacity`. The view changes a colour
  name (for example `"red"`) to RGBA with a small table of named colours.
- `screenshot(...)`, `run(...)` and `commands()` pass to the tool session.
- `show()` does nothing and returns `None`, so that notebooks that call
  `view.show()` still run.

### D7. MCP server (`loop_link.mcp`, extra `mcp`)

- Entry point: `python -m loop_link.mcp` (stdio).
- At start, connect with `connect()` and get the command list. Make one MCP
  tool for each command with `tool_available = true`. The tool name is the
  command name with `.` changed to `_` (`object_set_visible`). The input
  schema is the `input_schema` of the viewer.
- Extra tools: `screenshot` (returns an MCP image, PNG, default 1024 px
  wide), `pick` and `list_objects` (from `scene.inventory` on a short data
  session).
- A viewer error returns an MCP tool error with the code and the text.
- Register with Claude Code: `claude mcp add geoviewer -- python -m loop_link.mcp`.

### D8. `loop_common` import fix

Remove `import pyvista as pv` from the top of
`loop_common/geometry/_surface.py`. `vtk()` already imports pyvista inside
the function. Keep the type hint of `from_vtk` as a string
(`"pv.PolyData | str"`) under `from __future__ import annotations`, which is
already at the top of the file. A test checks that
`import loop_common.geometry` does not put `pyvista` in `sys.modules`
(FR-012).

### D9. Selection (story 7, phase F, waits for OP6)

What the GeoViewer spec must give (proposal for that spec):

- A command `selection.get` (tool available, no window needed). Result:
  `{"objects": [{"id": "...", "elements": {"association": "cell",
  "indices": [...]}}]}`. The indices are in the order of the arrays that the
  client sent. The result has a limit (for example 100,000 indices) and a
  field `truncated`.
- An opt-in event stream on the tool connection: the tool sends
  `events.subscribe` with a list (`selection.changed`, `pick`). The viewer
  then sends `selection.changed` (same body as `selection.get`) and `pick`
  (the same hit as `pick.result`) with no `request` number. Spec 035 of
  GeoViewer has "events to a tool" out of scope, so this is a new GeoViewer
  spec.
- A command `selection.set`, so that Python can select elements too (for
  example, "select the cells where grade > 5").

What `loop_link` adds:

- `ToolSession.selection()` returns a `Selection`: a list of
  `(object_id, association, indices)`, with indices as a numpy `int64`
  array.
- `ToolSession.wait_for_click(timeout=None)` returns the next hit.
- `GeoViewerLink.watch(callback, events=("selection.changed",))` runs a
  daemon thread with its own tool session. It calls `callback` for each
  event. It returns a handle with `stop()`. The thread never touches the
  scene. In Jupyter the callback runs on that thread; the docs say this.
- `GeoViewerView.selection()` maps object ids back to the features and the
  `loop_common` objects that the view sent, so that the user gets
  `(feature, object, association, indices)`.

## Test strategy

Write each test first and see it fail.

| Level | What | Where | Runs in CI |
|---|---|---|---|
| Unit | Frame of each message type equals the GeoViewer fixture after decode (SC-002) | `loop_link/tests/test_geoviewer_fixtures.py` | yes |
| Unit | Adapters: each `loop_common` type, property association, refusals, vector to orientation, node order | `loop_link/tests/test_adapters.py` (uses `loop_common` as a test dependency only) | yes |
| Unit | Discovery: sort order, stale file, env token, no token, no viewer (temporary settings folder) | `loop_link/tests/test_discovery.py` | yes |
| Unit | Tool session against the fake viewer: list, run, error, progress, screenshot, pick | `loop_link/tests/test_tool.py`, extend `geoviewer_fake_server.py` with `/tool` | yes |
| Unit | PNG writer | `loop_link/tests/test_png.py` | yes |
| Unit | numpy-only environment: import and push (SC-003) | new CI job: `pip install ./packages/loop_link pytest` and run the tests marked `minimal` | yes |
| Unit | `GeoViewerView` against the fake viewer: ids, replace, ignored arguments, colour commands | `loopstructural_visualisation/tests/test_geoviewer_view.py` | yes |
| Unit | `loop_common` does not import pyvista | `loop_common/tests/test_imports.py` | yes |
| End to end | All types to a real `geoviewer-headless`; far origin of 500 km (SC-001, SC-006) | `loop_link/tests/test_e2e_geoviewer.py`, marker `geoviewer`; skipped when `GEOVIEWER_HEADLESS` is not set | no (manual until GeoViewer is public) |
| Manual | Notebook: `claudius` model in `Loop3DView` and `GeoViewerView` (SC-004) | `packages/loop_link/examples/geoviewer_link.ipynb` | no |

## Phases

| Phase | Content | Stories | Can merge alone |
|---|---|---|---|
| A | Commit the existing `loop_link`; protocol 1.10; fixtures; data arrays; all message types; `loop_common` import fix | 3 (part), 5 | yes |
| B | Shapes and adapters | 3 | yes |
| C | Discovery and tool session; PNG writer | 2, 4 | yes |
| D | `GeoViewerView`; example notebook; ROADMAP entry | 1 | yes |
| E | MCP server | 6 | yes |
| F | Selection: read, wait for a click, watch (waits for the GeoViewer spec, OP6) | 7 | yes |

## Project structure

```
specs/003-geoviewer-link/
  spec.md
  plan.md
  tasks.md                       # next step
packages/loop_link/
  pyproject.toml                 # version 0.2.0; extra "mcp"
  src/loop_link/...              # see D1
  tests/
    fixtures/geoviewer/          # copy of GeoViewer fixtures + SOURCE.txt (OP5)
    geoviewer_fake_server.py     # extend: /tool path
    test_geoviewer_fixtures.py
    test_adapters.py
    test_discovery.py
    test_tool.py
    test_png.py
    test_e2e_geoviewer.py
packages/loopstructural_visualisation/
  pyproject.toml                 # extra "geoviewer"
  src/loopstructuralvisualisation/_geoviewer_view.py
  tests/test_geoviewer_view.py
packages/loop_common/
  src/loop_common/geometry/_surface.py
  tests/test_imports.py
packages/loop_link/examples/geoviewer_link.ipynb   # not in examples/: the docs build has no viewer
.github/workflows/               # job for the numpy-only test
```

## Risks

| Risk | Effect | Action |
|---|---|---|
| The GeoViewer protocol changes before GeoViewer moves into this repository | The fixtures are old, and the link sends frames that the viewer refuses | `SOURCE.txt` has the GeoViewer commit. The end-to-end test against a real viewer finds the drift. Update the copy with each GeoViewer protocol minor version. |
| `Loop3DView` methods change | `GeoViewerView` no longer has the same arguments | A test compares the signatures of the 6 methods in both classes. |
| A large model makes a frame larger than 256 MiB | The push fails | The message function refuses it before it sends. A later change can split a large Surface. |
| Two data clients (for example QGIS and a notebook) | The second one gets `busy` | Short sessions (one for each call). The error tells the user that another program is connected. |
| Commands change their names or inputs | `GeoViewerView` colour calls fail | The view reads the command list one time per view and checks that the commands it uses exist, with a clear error. |

## Complexity tracking

| Addition | Why it is necessary | Simpler choice that was rejected |
|---|---|---|
| A PNG writer in `loop_link` | Jupyter and MCP need PNG, and the base package must stay numpy-only (FR-001) | A dependency on PIL: it breaks QGIS use on some platforms. |
| `typing.Protocol` shapes | FR-002: no import of `loop_common`, and the QGIS plugin can send its own objects | Import `loop_common`: it brings pandas, pydantic, scipy, pyvista and pyyaml. |
| A tool session for colours (OP2) | The protocol cannot set the active array in an upsert | Wait for a GeoViewer protocol change: it blocks story 1. |

## Coverage of the spec

| Spec item | Design | Tests |
|---|---|---|
| Story 1, FR-008, FR-009, SC-004 | D6 | `test_geoviewer_view.py`, notebook |
| Story 2, FR-005, SC-005 | D4 | `test_discovery.py` |
| Story 3, FR-002, FR-003, FR-004, SC-001, SC-006 | D2, D3 | `test_adapters.py`, `test_e2e_geoviewer.py` |
| Story 4, FR-006, FR-007 | D5 | `test_tool.py`, `test_png.py` |
| Story 5, FR-001, SC-003 | D1, D5 (PNG) | numpy-only CI job |
| Story 6, FR-011 | D7 | MCP tests (phase E) |
| FR-010, SC-002 | D2 | `test_geoviewer_fixtures.py` |
| FR-012 | D8 | `test_imports.py` |
| Story 7, FR-013 | D9 | `test_tool.py` (fake viewer with events), e2e after the GeoViewer spec |

## Answers

- 2026-10-29: Test of the link against a real GeoViewer (debug build of
  2026-10-29, protocol 1.10): `loop_link` push of a Group and a Surface
  passed; a `Points` upsert with a `float` array passed, but the points were
  one colour until `colour.set_active` ran (this gave OP2); the tool session
  passed for `commands.list`, `command.run` and a screenshot.
