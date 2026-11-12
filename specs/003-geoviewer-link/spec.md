# Feature spec: Python link to GeoViewer

**Feature**: `003-geoviewer-link` | **Created**: 2026-10-29 | **Status**: Draft, with plan and tasks (clarify before implement)

**Input**: The user wants to send LoopStructural models and data from Python
(a script, a Jupyter notebook or a QGIS plugin) to a running GeoViewer, and to
control what GeoViewer shows. The same link must later let Claude control the
viewer. The user does not want a second set of Python object definitions: the
object types of `loop_common.geometry` are the only ones. GeoViewer is mainly a
viewer for Loop products, and it can move into this repository when it is
public.

<!--
A spec says WHAT the user needs and WHY. It does not say HOW.
Write in ASD-STE100 Simplified Technical English.
-->

## Context

- GeoViewer is a 3D viewer in Rust. It listens on `127.0.0.1` (default port
  47615) for WebSocket clients with a bearer token. Its protocol is in
  `docs/protocol.md` of the GeoViewer repository (version 1.10 on
  2026-10-29).
- GeoViewer has two kinds of connection:
  - A **data client** (path `/`) sends objects: `scene.upsert`, `scene.data`,
    `scene.style`, `scene.remove`, `scene.clear`. Only one data client can
    connect at one time.
  - A **tool** (path `/tool`) runs the commands of the viewer (78 on
    2026-10-29, each with a JSON schema), takes screenshots and picks objects.
    At most 8 tools can connect at one time.
- The package `packages/loop_link` exists on the branch
  `feat/loop-geoviewer-client`. It is staged, not committed. It has a WebSocket
  client with the standard library only, a binary frame codec, a short push
  session, and the GeoViewer messages for `Surface` and `Group` only. It sends
  protocol version 1.8.
- A test on 2026-10-29 against a real GeoViewer (protocol 1.10) passed for:
  `loop_link` push of a Group and a Surface; a data client with `Points` and a
  `float` array; and a tool with `commands.list`, `command.run` and a
  screenshot.
- `loop_common.geometry` has `Surface`, `ValuePoints`, `VectorPoints`,
  `StructuredGrid2DGeometry`, `StructuredGrid3DGeometry` and
  `UnstructuredMeshGeometry`. The features of a `GeologicalModel` return these
  objects (`surfaces()`, `get_data()`). `Loop3DView` in
  `loopstructural_visualisation` changes them to pyvista meshes.
- A QGIS plugin can use `loop_link` only if `loop_link` needs numpy and
  nothing more. `loop_common` needs pandas, pydantic, scipy, pyvista and
  pyyaml.

## User scenarios and tests

### User story 1: Show a model in GeoViewer from a notebook (priority: P1)

A geologist builds a model in a Jupyter notebook. They want to see it in
GeoViewer with the same calls that they use for `Loop3DView`.

**Why this priority**: this is the main purpose. Without it, a user must
export files and open them by hand.

**Independent test**: start GeoViewer. In a notebook, build the
`claudius` example model. Call `plot_model_surfaces`, `plot_data` and
`plot_scalar_field` on a `GeoViewerView`. Take a screenshot and compare it with
the `Loop3DView` result by eye.

**Acceptance scenarios**:

1. **Given** a running GeoViewer and a model, **when** the user calls
   `GeoViewerView().plot_model_surfaces(model)`, **then** each surface of the
   model shows in GeoViewer, in its true position, in one group.
2. **Given** a view, **when** the user calls a plot method a second time for
   the same feature, **then** GeoViewer replaces the old object. It does not
   show two copies.
3. **Given** a view, **when** the user gives `cmap`, `vmin` and `vmax`,
   **then** GeoViewer colours the object by its values with this colour map
   and range.
4. **Given** a call with an argument that only pyvista knows (for example
   `pyvista_kwargs`), **when** the call runs, **then** the link ignores the
   argument and logs one warning.

### User story 2: Find the viewer with no copy and paste (priority: P1)

A user wants to connect with `connect()` and no arguments.

**Why this priority**: copying the port and the token for each session is
slow, and users put tokens in notebooks that they share.

**Independent test**: start GeoViewer and save a token. Call `connect()` in a
new Python process with no arguments. Check that the push works.

**Acceptance scenarios**:

1. **Given** one running GeoViewer with a saved token, **when** the user calls
   `connect()`, **then** the link finds the port and the token by itself.
2. **Given** two running viewers, **when** the user calls `connect()`, **then**
   the link uses the viewer with a window before a headless viewer, and then
   the viewer that had the focus most recently.
3. **Given** no running viewer, **when** the user calls `connect()`, **then**
   the link gives an error that tells the user to start GeoViewer. It does not
   start a viewer.
4. **Given** a token in the environment variable `GEOVIEWER_TOKEN`, **when**
   the user calls `connect()`, **then** the link uses this token before the
   saved token.

### User story 3: Send all object types of `loop_common` (priority: P1)

A script sends points, vectors, surfaces, grids and meshes from
`loop_common.geometry` with their properties.

**Why this priority**: the plot methods of story 1 need these types.

**Independent test**: make one object of each type in
`loop_common.geometry`, with one vertex property and (where the type has
cells) one cell property. Send each one. Check that GeoViewer refuses none.

**Acceptance scenarios**:

1. **Given** an object of a supported type, **when** the link sends it,
   **then** GeoViewer shows it, with each property as a data array.
2. **Given** a `VectorPoints`, **when** the link sends it, **then** GeoViewer
   shows a disc at each point, normal to the vector.
3. **Given** an object with coordinates far from the origin (more than 4 km),
   **when** the link sends it, **then** the position in GeoViewer is correct
   to 1 mm.
4. **Given** an object that GeoViewer cannot show correctly (for example, a
   3D grid with a rotation), **when** the link sends it, **then** the link
   refuses it before it sends, with an error that names the reason.
5. **Given** an object with a NaN coordinate or an index outside the
   vertices, **when** the link sends it, **then** the link refuses it before
   it sends.

### User story 4: Control the view and get a picture back (priority: P2)

A notebook user wants to set the camera, the colours and the visible objects,
and to show a picture of the view in the notebook.

**Why this priority**: a notebook records the result. A script that makes
figures needs the picture.

**Independent test**: send a model. Run `view.standard`, `colour.set_active`
and `object.set_visible` from Python. Call `screenshot()` and show the image
in the notebook.

**Acceptance scenarios**:

1. **Given** a running viewer, **when** the user asks for the command list,
   **then** the link returns each command with its name, description and input
   schema.
2. **Given** a command name and an input, **when** the user runs it, **then**
   the link returns the result of the viewer, or raises an error with the code
   and the text of the viewer (for example `invalid_input` and the field name).
3. **Given** a running viewer, **when** the user calls `screenshot()`, **then**
   the link returns an RGBA numpy array. In Jupyter, the image shows in the
   output of the cell.
4. **Given** a screenshot of 4096 by 4096 pixels, **when** the user asks for
   it, **then** the link accepts the reply (64 MiB).

### User story 5: Use the link from QGIS (priority: P2)

The LoopStructural QGIS plugin sends a model to GeoViewer.

**Why this priority**: QGIS users are a main group of Loop users.

**Independent test**: in a Python environment with numpy only, import
`loop_link` and push a surface to a fake viewer.

**Acceptance scenarios**:

1. **Given** an environment with numpy and no other package, **when** the
   user imports `loop_link` and sends objects, **then** this works.
2. **Given** an object that has the attributes of a `loop_common` type, but
   that is not of that class, **when** the link sends it, **then** this works.

### User story 6: Let Claude control the viewer (priority: P3)

A user asks Claude Code to show or change things in GeoViewer.

**Why this priority**: useful, but it needs stories 2 and 4 first.

**Independent test**: register the MCP server with Claude Code. Ask Claude to
hide an object and to show a screenshot.

**Acceptance scenarios**:

1. **Given** the MCP server, **when** Claude lists the tools, **then** each
   command that a tool can run is one MCP tool, with the schema of the viewer.
2. **Given** a screenshot tool call, **when** it runs, **then** Claude gets a
   PNG image.
3. **Given** a new command in the viewer, **when** the MCP server starts,
   **then** the new command is a tool with no change to the MCP server.

### User story 7: Read what the user selects in GeoViewer (priority: P2, waits for GeoViewer)

A user clicks objects, points or cells in GeoViewer (in the 3D view or in the
property table). A notebook reads the selection: which objects, and which
vertices or cells of each one, with their data values.

**Why this priority**: it lets a user find data in 3D and then work on it in
Python (for example, remove bad points, or look at the values of selected
cells).

**Waits for**: a GeoViewer spec. On 2026-10-29, GeoViewer has no command that
returns the selection, and it sends no events to a tool. A click gives a
`pick.result` to a page of the browser bundle only.

**Independent test**: send a surface with a cell property. In GeoViewer,
select 3 cells in the property table. In Python, read the selection. Check the
object id, the association `cell` and the 3 indices.

**Acceptance scenarios**:

1. **Given** a selection in GeoViewer, **when** Python asks for it, **then**
   the link returns each selected object id, and for each one the association
   (`vertex` or `cell`) and the indices.
2. **Given** a selection, **when** Python asks for it, **then** the indices
   are the indices of the arrays that the link sent, so that
   `surface.properties["x"][indices]` gives the selected values.
3. **Given** a Python callback for selection changes, **when** the user
   selects something in GeoViewer, **then** the callback gets the new
   selection within 0.5 s.
4. **Given** a click on an object, **when** Python waits for the next click,
   **then** the link returns the hit (object, association, index, position,
   values).

### Edge cases

- The viewer stops in the middle of a push. The link raises an error that
  names the objects that were sent. The scene of the viewer keeps them.
- Another data client is connected. The viewer answers `busy`. The link
  raises an error that says that another program is connected.
- The viewer has an origin already, and it is different from the origin of
  the client. The link uses the origin of the viewer.
- The viewer has a newer minor protocol version. The link works. The viewer
  has a new major version. The link raises an error.
- A property has the wrong length. The link refuses the object before it
  sends.
- A property is not a number (for example, text or a category). The link
  sends it as a `text` or `referenced` array.
- A frame is larger than 256 MiB. The link refuses it before it sends.
- The instance file of a viewer that stopped is still on disk. The link checks
  that the viewer answers before it uses it.

## Requirements

### Functional requirements

- **FR-001**: `loop_link` must need numpy and the Python standard library
  only. Other packages are optional extras.
- **FR-002**: `loop_link` must not define geometry classes. It must read
  objects through their attributes, as defined by the types of
  `loop_common.geometry`, and it must not import `loop_common`.
- **FR-003**: `loop_link` must send these types: `Surface` to `Surface`,
  `ValuePoints` to `Points`, `VectorPoints` to `Points` with an
  `orientation` property group, `StructuredGrid2DGeometry` to `Grid2D`,
  `StructuredGrid3DGeometry` to `BlockModel`, `UnstructuredMeshGeometry` to
  `TetraMesh`, and also groups. It must send each property as a data array,
  with `vertex` or `cell` association.
- **FR-004**: `loop_link` must refuse, before it sends, an object that
  GeoViewer cannot show in its true position or that GeoViewer would refuse.
  The error must name the object and the reason.
- **FR-005**: `loop_link` must find a running viewer from the instance files
  and the saved token of GeoViewer, and from `GEOVIEWER_TOKEN`.
- **FR-006**: `loop_link` must run the commands of the viewer, list them with
  their schemas, take screenshots and pick, through the tool connection.
- **FR-007**: `loop_link` must give a viewer error as a Python exception with
  the code, the text and the field of the viewer.
- **FR-008**: `loopstructural_visualisation` must have a `GeoViewerView` with
  the same names and arguments as the `Loop3DView` methods
  `plot_surface`, `plot_scalar_field`, `plot_data`, `plot_model_surfaces`,
  `plot_block_model` and `plot_vector_field`.
- **FR-009**: `GeoViewerView` must give each object a stable id from the
  feature name, so that a second call replaces the object.
- **FR-010**: `loop_link` must check its frames against the protocol fixtures
  of GeoViewer.
- **FR-011**: An MCP server must make one MCP tool from each command that a
  tool can run, plus a screenshot tool that returns a PNG. It is an optional
  extra.
- **FR-012**: `import loop_common.geometry` must not import pyvista.
- **FR-013**: When GeoViewer gives them (see story 7), `loop_link` must read
  the selection (object ids, association, indices) and must let Python wait
  for or subscribe to selection changes and clicks.

### Protocol and data (if the feature changes them)

- No change to the GeoViewer protocol. The link uses protocol 1.10.
- The link reads the GeoViewer files `instances/<pid>.json` and `link.json`
  in the settings folder (`%APPDATA%\geoviewer` on Windows,
  `$HOME/.geoviewer` on Linux and macOS). It does not write them.

### Key entities

- **Link**: the address of one viewer (host, port, token).
- **Data session**: a short connection on `/`: `hello`, objects, close.
- **Tool session**: a connection on `/tool` for commands, screenshots and
  picks.
- **Adapter**: a function that changes one object of a `loop_common` type to a
  `scene.upsert` frame.
- **GeoViewerView**: the notebook class with the `Loop3DView` method names.

## Success criteria

- **SC-001**: 100 % of the `loop_common.geometry` types in FR-003 go to
  GeoViewer with no error from the viewer, in the test against a real viewer.
- **SC-002**: The frames of `loop_link` are equal, byte for byte after
  decode, to the GeoViewer fixtures for each type in FR-003.
- **SC-003**: `loop_link` imports and pushes in an environment with numpy only
  (CI job).
- **SC-004**: A user changes a notebook from `Loop3DView` to `GeoViewerView`
  by changing one line, for the 6 methods of FR-008.
- **SC-005**: `connect()` with no arguments works in 100 % of the cases where
  one viewer runs and a token is saved.
- **SC-006**: A position far from the origin (500 km) has an error of 1 mm or
  less in GeoViewer.

## Out of scope

- Changes to GeoViewer itself. Gaps in GeoViewer go to a GeoViewer spec (for
  example, a BlockModel with a rotation).
- A move of GeoViewer into this repository.
- Drillholes, curves and images. `loop_common` has no type for them yet.
- An assistant inside GeoViewer.
- A viewer in a notebook cell (the GeoViewer browser bundle).
- The GeoViewer side of story 7 (a selection command and selection events).
  It goes in a GeoViewer spec.

## Clarifications

- 2026-10-29: Where does `loop_link` live? In `LoopStructural/packages`,
  because GeoViewer is mainly a viewer for Loop products and can move into
  this repository. (The user.)
- 2026-10-29: Which object definitions? Only those of `loop_common`; no
  second set in `loop_link`. (The user.)
