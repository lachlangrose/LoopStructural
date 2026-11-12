# Tasks: Python link to GeoViewer

**Input**: `specs/003-geoviewer-link/` (`spec.md`, `plan.md`)
**Prerequisites**: `plan.md` (required), `spec.md` (required for the user stories)

<!-- Written in ASD-STE100 Simplified Technical English. -->

## Orchestrator notes

- **Worktree**: `LoopStructural.worktree/geoviewer-client`, branch
  `feat/loop-geoviewer-client`. Do not switch the branch of the main checkout.
  The branch is older than `master` (it has no `specs/001`). Task T001 asks
  the user about this.
- **Rules for each sub agent**: read `plan.md` (sections D1 to D9 and the open
  points); change only the files in the task `Files` list; for a test task,
  run the test and see it fail (or be skipped, where the task says so); write
  comments and docs in ASD-STE100 Simplified Technical English; use numpy
  docstrings and type hints (ruff `D`, `ANN`); keep Python 3.9 syntax in
  `loop_link` (`from __future__ import annotations` for `X | Y` hints).
- **No new required dependency in `loop_link`** (FR-001). Only numpy and the
  standard library. A test that needs `loop_common`, PIL or `mcp` uses
  `pytest.importorskip`.
- **GeoViewer reference**: `C:/Users/lachl/dev/geoviewer` (`docs/protocol.md`,
  `fixtures/protocol/expected/`), protocol 1.10. Read it. Do not change it.
- **Tiers**: `[S]` = send to a small, fast model. `[M]` = send to the
  standard model. If an `[S]` task fails twice, send it to `[M]`. The role
  names in `.agents/model-policy.json` are `worker-S` and `worker-M`.
- **Waves**: 10 waves for phases A to E, and 4 more for phase F. Start a wave
  when all `Needs` of its tasks are done. Run the tasks of a wave in parallel.
  A task with `Files: none` runs alone.
- **After each wave**: run the tests of each package that the wave changed:
  - `uv run --package loop-link pytest packages/loop_link/tests -q`
  - `uv run --package loop_common pytest packages/loop_common/tests -q`
  - `uv run --package loopstructuralvisualisation pytest packages/loopstructural_visualisation/tests -q`

  Then run `ruff check packages/loop_link packages/loop_common packages/loopstructural_visualisation`.
  Fix a failure before the next wave.
- **Checkpoints**:
  - After T014 (end of phase A): all fixture tests pass (SC-002).
  - After T024 (end of phase B): all adapter tests pass.
  - After T036 (end of phase C): the tool tests pass against the fake viewer.
  - After T053 (end of phase D): run T073 against a real `geoviewer-headless`
    if one is built, and run the notebook of T055 by hand.
- **Blocked tasks**: do not start a task with `Blocked by` before the user
  confirms the open point. Phase F waits for OP6 (a GeoViewer spec).
- **Before done**: `black --check packages/loop_link packages/loopstructural_visualisation packages/loop_common`,
  `ruff check` (as above), and the three pytest commands above.
- **Commits**: Conventional Commits, `type(scope): description`, for example
  `feat(loop-link): add tool session`. Scope the commits to the package so
  that release-please counts them for the right package. Do not commit unless
  the user asks.

## Phase A: Setup, protocol 1.10, fixtures, import fix

- [ ] T001 [Setup] [M] Ask the user two questions, and do what they say.
  - Do: Ask if the staged `packages/loop_link` files can be committed as
    `feat(loop-link): add loop_link package`.
  - Do: Ask if `master` can be merged into `feat/loop-geoviewer-client` now,
    so that the branch has `specs/001` and the newest packages.
  - Files: none
  - Needs: none
  - Wave: 1
  - Done when: the user answered both questions and `git status` shows the
    state that the user asked for.
- [ ] T002 [P] [Setup] [S] Add `loop_link` to the package CI matrix.
  - Do: In the `packages-test` matrix add `- { name: loop-link, dir: loop_link }`.
  - Files: `.github/workflows/packages.yml`
  - Needs: T001
  - Wave: 2
  - Done when: `python -c "import yaml; d=yaml.safe_load(open('.github/workflows/packages.yml')); assert {'name':'loop-link','dir':'loop_link'} in d['jobs']['packages-test']['strategy']['matrix']['package']"` exits 0.
- [ ] T003 [P] [Setup] [S] Set the extras and the test markers of `loop_link`.
  - Do: In `[project.optional-dependencies]` set
    `tests = ["pytest", "loop-common"]` and
    `mcp = ["mcp>=1.2; python_version >= '3.10'"]`.
  - Do: Add `[tool.uv.sources]` `loop-common = { workspace = true }`.
  - Do: In `tests/conftest.py` add `pytest_configure` that registers the
    markers `minimal` (needs numpy only) and `geoviewer` (needs a real
    `geoviewer-headless`).
  - Files: `packages/loop_link/pyproject.toml`, `packages/loop_link/tests/conftest.py`
  - Needs: T001
  - Wave: 2
  - Done when: `uv sync --package loop-link --extra tests` exits 0 and
    `uv run --package loop-link pytest packages/loop_link/tests --markers`
    lists `minimal` and `geoviewer`.
- [ ] T010 [P] [Setup] [S] Copy the GeoViewer protocol fixtures (OP5).
  - Do: Copy all files of `C:/Users/lachl/dev/geoviewer/fixtures/protocol/expected/`
    to `packages/loop_link/tests/fixtures/geoviewer/`.
  - Do: Write `SOURCE.txt` with the GeoViewer commit
    (`git -C C:/Users/lachl/dev/geoviewer rev-parse HEAD`), the date, and the
    protocol version 1.10.
  - Files: `packages/loop_link/tests/fixtures/geoviewer/*`
  - Needs: T001
  - Wave: 2
  - Done when: the folder has `upsert_surface.json`, `upsert_points.json`,
    `upsert_points_orientation.json`, `upsert_grid2d.json`,
    `upsert_blockmodel_arrays.json`, `upsert_tetramesh.json`,
    `upsert_group.json`, `style.json`, `data.json`, `remove.json`,
    `clear.json`, `hello.json` and `SOURCE.txt`.
- [ ] T011 [Test] [M] Write the fixture tests (FR-010, SC-002).
  - Do: For each fixture of T010 except `hello`, `clear` and `remove`, call the
    message function of `geoviewer/protocol.py` with the values of the
    fixture. Decode the frame (header and buffers) and compare it with the
    fixture JSON. Compare floats with `numpy.allclose` and all other values
    exactly.
  - Do: Use the API of plan D2: `surface_message`, `points_message`,
    `grid2d_message`, `blockmodel_message`, `tetramesh_message`,
    `group_message`, `style_message`, `data_message`, and
    `data_array(array_id, name, values, association, *, colour_map=None, value_map=None)`,
    which returns `(entry, buffers)`.
  - Do: Add a test that `PROTOCOL_VERSION == {'major': 1, 'minor': 10}`.
  - Do: Mark the file `pytestmark = pytest.mark.minimal`.
  - Files: `packages/loop_link/tests/test_geoviewer_fixtures.py`
  - Needs: T003, T010
  - Wave: 3
  - Done when: the tests run and fail because the functions do not exist yet.
- [ ] T012 [P] [Test] [M] Write the unit tests for data arrays and the coordinate rule (D2).
  - Do: `data_array` gives `float`/`f32` for a float array and keeps NaN;
    `integer`/`i32` for ints in range; refuses an int outside the `i32` range
    with `ProtocolError`; `boolean`/`u8` for bool; `text` with a `u8` buffer
    and `u32` offsets for strings (check `[0, ...]` offsets and UTF-8).
  - Do: A message refuses a data array of the wrong length, with the object
    name in the error.
  - Do: Coordinates within 4000 m of the origin go as `f32`; others as
    `f64`; a point 500 km from the origin keeps 1 mm.
  - Do: Keep the existing tests in the file.
  - Files: `packages/loop_link/tests/test_geoviewer_protocol.py`
  - Needs: T003
  - Wave: 3
  - Done when: the new tests run and fail; the old tests still pass.
- [ ] T013 [Core] [M] Bring `protocol.py` to 1.10 and add data arrays (D2).
  - Do: Set `PROTOCOL_VERSION` to 1.10. Add `data_array` and the internal
    coordinate function (subtract the origin in `f64`, then `f32` or `f64`).
  - Do: Add `data` and `property_groups` arguments to `surface_message`.
  - Files: `packages/loop_link/src/loop_link/geoviewer/protocol.py`
  - Needs: T011, T012
  - Wave: 4
  - Done when: the tests of T012 pass, and the Surface and Group cases of
    T011 pass.
- [ ] T014 [Core] [M] Add the other message functions (D2).
  - Do: Add `points_message`, `grid2d_message`, `blockmodel_message`,
    `tetramesh_message`, `style_message` and `data_message`, each with the
    checks of `docs/protocol.md` (lengths, NaN and infinite coordinates,
    index ranges, cell counts and sizes more than 0, Grid2D dip 0 to 90).
  - Do: Property groups: check the members of the roles `orientation` and
    `lineation` as in `docs/protocol.md` "Property groups".
  - Files: `packages/loop_link/src/loop_link/geoviewer/protocol.py`
  - Needs: T013
  - Wave: 5
  - Done when: all tests of T011 and T012 pass.
- [ ] T015 [P] [Test] [S] Test that `loop_common.geometry` does not import pyvista (FR-012).
  - Do: In a subprocess (`sys.executable -c ...`), import `loop_common.geometry`
    and check that `"pyvista" not in sys.modules`.
  - Files: `packages/loop_common/tests/test_imports.py`
  - Needs: T001
  - Wave: 2
  - Done when: the new test runs and fails.
- [ ] T016 [Core] [S] Remove the top import of pyvista from `_surface.py` (D8).
  - Do: Remove `import pyvista as pv` from the top. Keep the import inside
    `vtk()`. Add an import inside `from_vtk`. Keep the type hints as strings.
  - Files: `packages/loop_common/src/loop_common/geometry/_surface.py`
  - Needs: T015
  - Wave: 3
  - Done when: the test of T015 passes and all `loop_common` tests pass.

## Phase B: Adapters from `loop_common` types (user story 3)

- [ ] T020 [P] [Core] [M] Write the attribute shapes (D3).
  - Do: One `typing.Protocol` for each type in the table of plan D3, with
    only the attributes that the adapter reads. Use `runtime_checkable` so
    that the adapter can select by shape. No logic.
  - Files: `packages/loop_link/src/loop_link/geoviewer/shapes.py`
  - Needs: T001
  - Wave: 2
  - Done when: `python -c "import loop_link.geoviewer.shapes"` exits 0 and
    ruff passes on the file.
- [ ] T021 [Test] [M] Write the adapter tests (D3, story 3, story 5 scenario 2).
  - Do: For each `loop_common` type (with `pytest.importorskip("loop_common")`),
    `adapters.to_message(obj, object_id, origin)` gives a frame that decodes
    to the right `object_type`, geometry and params.
  - Do: The same with a `types.SimpleNamespace` that has the same attributes
    (no `loop_common`). Mark this test `minimal`.
  - Do: Properties: the node count gives `vertex`, the cell count gives `cell`,
    any other length raises `ProtocolError` with the name.
  - Do: `Surface.values` and `ValuePoints.values` become an array named
    `values`.
  - Do: Refusals: `rotation_xy` other than 0 (OP1), an object that matches no
    shape (`TypeError`).
  - Do: `UnstructuredMeshGeometry` with 10 columns in `elements` sends only
    the first 4.
  - Do: `StructuredGrid2DGeometry` with `z=125.0` gives a Grid2D origin with
    z 125 (OP3).
  - Files: `packages/loop_link/tests/test_adapters.py`
  - Needs: T020
  - Wave: 3
  - Done when: the tests run and fail because `adapters.py` does not exist.
- [ ] T022 [P] [Test] [S] Test the node order of the `loop_common` grids.
  - Do: For a `StructuredGrid3DGeometry` with `nsteps=(3, 4, 5)`, check that
    node `i + nx * (j + ny * k)` of `grid.nodes` is at
    `origin + (i, j, k) * step_vector` (`nx = 3`, `ny = 4`). Do the same with
    two axes for `StructuredGrid2DGeometry`.
  - Do: `pytest.importorskip("loop_common")`.
  - Files: `packages/loop_link/tests/test_node_order.py`
  - Needs: T003
  - Wave: 3
  - Done when: the test passes (it checks a fact of `loop_common`; if it
    fails, stop and tell the user, because plan D3 is then wrong).
- [ ] T023 [P] [Test] [M] Write the tests for vectors to orientations (D3.1).
  - Do: `(0, 0, 1)` gives dip 0 and polarity 1; `(1, 0, 1)` gives dip
    direction 90 and dip 45; `(0, 1, -1)` gives polarity 0 and dip
    direction 180 and dip 45; `(0, 0, 0)` gives NaN, NaN, polarity -1.
  - Do: The frame has a property group with role `orientation` and the
    members `dip_direction`, `dip`, `polarity`, and an array `magnitude`.
  - Do: `kind='lineation'` gives a `lineation` group with `trend` and
    `plunge`.
  - Do: Mark the file `minimal`. Use `SimpleNamespace` objects.
  - Files: `packages/loop_link/tests/test_orientation.py`
  - Needs: T003
  - Wave: 3
  - Done when: the tests run and fail.
- [ ] T024 [Core] [M] Write the adapters (D3, D3.1).
  - Do: `to_message(obj, object_id, origin, *, parent=None, name=None, **options)`
    and one function for each type. Select by shape, in the order of the
    table in plan D3. Options: `properties` (grids), `z` (Grid2D),
    `kind` (VectorPoints), `colour_map`.
  - Do: Export `to_message` from `loop_link.geoviewer`.
  - Files: `packages/loop_link/src/loop_link/geoviewer/adapters.py`, `packages/loop_link/src/loop_link/geoviewer/__init__.py`
  - Needs: T014, T021, T022, T023, T036
  - Wave: 6
  - Done when: the tests of T021 and T023 pass.

## Phase C: Discovery, tool session, PNG (user stories 2 and 4)

- [ ] T030 [Test] [M] Write the discovery tests (D4, story 2).
  - Do: Use `tmp_path` as the settings folder: monkeypatch `APPDATA` (Windows)
    and `HOME` (other systems). Write instance files and `link.json` there.
  - Do: Cases: one viewer; a `window` and a `headless` viewer (the window
    wins); two windows (the newest `focused` wins); a stale file (no
    listener on its port) is skipped and not deleted; `GEOVIEWER_TOKEN` wins
    over `link.json`; an empty `GEOVIEWER_TOKEN` is not a token; no viewer
    gives the "Start GeoViewer" error; no token gives the "New random token"
    error; given `port` and `token` arguments win.
  - Do: Use a plain TCP listener on `127.0.0.1:0` as the "answering" viewer.
  - Do: Check that no error text and no log line contains the token.
  - Do: Mark the file `minimal`.
  - Files: `packages/loop_link/tests/test_discovery.py`
  - Needs: T003
  - Wave: 3
  - Done when: the tests run and fail.
- [ ] T031 [Core] [M] Write discovery and `connect()` (D4).
  - Files: `packages/loop_link/src/loop_link/geoviewer/discovery.py`, `packages/loop_link/src/loop_link/geoviewer/link.py`, `packages/loop_link/src/loop_link/geoviewer/__init__.py`
  - Needs: T030
  - Wave: 4
  - Done when: the tests of T030 pass and the old link tests pass.
- [ ] T032 [P] [Test] [M] Add the `/tool` path to the fake viewer.
  - Do: On the path `/tool` the fake viewer answers: `commands.list` (three
    commands, with `input_schema`, `result_schema`, `needs_window`,
    `tool_available`, and the reply field `viewer`); `command.run` (two
    `command.progress` messages, then `command.result`; a `request.error`
    with `invalid_input` and a `field` for a bad input; `unknown_command`
    for an unknown name); `screenshot.request` (an RGBA gradient of the
    asked size); `pick.request` (one hit).
  - Do: A second data connection, while one is open, gets an `error` with
    the code `busy`, as the real viewer does.
  - Do: Record each request, so that tests can check what a client sent.
  - Do: The data path `/` stays as it is.
  - Files: `packages/loop_link/tests/geoviewer_fake_server.py`
  - Needs: T001
  - Wave: 2
  - Done when: the old tests still pass.
- [ ] T033 [P] [Test] [S] Write the PNG writer tests.
  - Do: `png.encode_rgba(array)` gives bytes that start with the PNG
    signature, with an `IHDR` of the right width, height, bit depth 8 and
    colour type 6, and valid CRCs.
  - Do: If PIL is installed, read the PNG back and compare the pixels.
  - Do: A wrong shape or dtype raises `ValueError`. Mark the file `minimal`.
  - Files: `packages/loop_link/tests/test_png.py`
  - Needs: T003
  - Wave: 3
  - Done when: the tests run and fail.
- [ ] T034 [Core] [S] Write the PNG writer (D5).
  - Files: `packages/loop_link/src/loop_link/png.py`
  - Needs: T033
  - Wave: 4
  - Done when: the tests of T033 pass.
- [ ] T035 [Test] [M] Write the tool session tests (D5, story 4).
  - Do: Against the fake viewer of T032: `commands()` gives three `Command`
    objects; `run()` gives the result and calls a progress callback two
    times; a bad input raises `ViewerError` with `code`, `message` and
    `field`; `screenshot(64, 32)` gives a `(32, 64, 4)` `uint8` array, and
    `_repr_png_()` gives PNG bytes; `pick_ray` and `pick_screen` give the
    hit; a reply larger than 16 MiB (for example a 2100 by 2100 screenshot)
    is accepted.
  - Do: A `push` while another data session is open raises `LinkError` with
    a text that says that another program is connected (edge case `busy`).
  - Do: Mark the file `minimal`.
  - Files: `packages/loop_link/tests/test_tool.py`
  - Needs: T032
  - Wave: 3
  - Done when: the tests run and fail.
- [ ] T036 [Core] [M] Write the tool session (D5).
  - Do: `ToolSession`, `Command`, `Screenshot`, `ViewerError`, and
    `GeoViewerLink.tools()`. Add a `max_incoming` argument to
    `WebSocketClient.connect` (default stays 16 MiB; the tool session uses
    300 MiB).
  - Files: `packages/loop_link/src/loop_link/geoviewer/tool.py`, `packages/loop_link/src/loop_link/websocket_client.py`, `packages/loop_link/src/loop_link/geoviewer/link.py`, `packages/loop_link/src/loop_link/geoviewer/__init__.py`
  - Needs: T031, T034, T035
  - Wave: 5
  - Done when: the tests of T035 pass and all other `loop_link` tests pass.

## Phase D: `GeoViewerView` (user story 1)

- [ ] T050 [P] [Setup] [S] Add the extra `geoviewer` to `loopstructural_visualisation`.
  - Do: `geoviewer = ["loop-link"]` in `[project.optional-dependencies]`, and
    `loop-link` in `tests`. Add `[tool.uv.sources]`
    `loop-link = { workspace = true }`.
  - Files: `packages/loopstructural_visualisation/pyproject.toml`
  - Needs: T001
  - Wave: 2
  - Done when: `uv sync --package loopstructuralvisualisation --extra tests`
    exits 0 and `uv run --package loopstructuralvisualisation python -c "import loop_link"` exits 0.
- [ ] T051 [Test] [M] Test that the method signatures agree with `Loop3DView` (FR-008, SC-004).
  - Do: For `plot_surface`, `plot_scalar_field`, `plot_data`,
    `plot_model_surfaces`, `plot_block_model` and `plot_vector_field`, the
    parameter names and defaults of `GeoViewerView` are equal to those of
    `Loop3DView` (`inspect.signature`, without `self`).
  - Files: `packages/loopstructural_visualisation/tests/test_geoviewer_view_signatures.py`
  - Needs: T050
  - Wave: 3
  - Done when: the test runs and fails because `GeoViewerView` does not exist.
- [ ] T052 [Test] [M] Test `GeoViewerView` against the fake viewer (D6, story 1).
  - Do: Use the fake viewer of `packages/loop_link/tests/geoviewer_fake_server.py`
    (import it by path, or copy it into this test folder as a fixture). Use a
    small model from `LoopStructural.datasets` (for example `load_claudius`).
  - Do: Check: the ids follow `<group>/<feature>/<kind>[/<index>]`; a second
    call for the same feature sends `scene.remove` for objects that are not
    sent again; `pyvista_kwargs` and `slicer` log one warning each, one time
    for each view; `cmap`, `vmin`, `vmax` send `colour.set_active`,
    `colour.set_map` and `colour.set_range` on the tool path;
    `colour="red"` sends `object.set_colour` with RGBA `[255, 0, 0, 255]`;
    `show()` returns `None`; `plot_model_surfaces` makes one `Group` for each
    feature.
  - Files: `packages/loopstructural_visualisation/tests/test_geoviewer_view.py`
  - Needs: T032, T050
  - Wave: 3
  - Done when: the tests run and fail.
- [ ] T053 [Core] [M] Write `GeoViewerView` (D6).
  - Do: Do not import pyvista in the module. Get the objects from the
    features in the same way as `Loop3DView`. Use `loop_link.geoviewer`
    (`connect`, `to_message`, `push`, `tools`). Add a small table of named
    colours. Check one time for each view that the commands it uses are in
    the command list, with a clear error.
  - Do: Export `GeoViewerView` from the package `__init__` with a lazy import,
    so that the package works without `loop_link`.
  - Files: `packages/loopstructural_visualisation/src/loopstructuralvisualisation/_geoviewer_view.py`, `packages/loopstructural_visualisation/src/loopstructuralvisualisation/__init__.py`
  - Needs: T024, T036, T051, T052
  - Wave: 7
  - Done when: the tests of T051 and T052 pass, and all
    `loopstructural_visualisation` tests pass.
- [ ] T055 [Docs] [M] Write the example notebook (SC-004).
  - Do: Build the `claudius` model. Show it with `Loop3DView`, then with
    `GeoViewerView` (one line changed). Call `screenshot()` so that the image
    shows in the notebook. Add a short text on `connect()` and the token.
  - Do: Save the notebook with no outputs.
  - Files: `packages/loop_link/examples/geoviewer_link.ipynb`
  - Needs: T053
  - Wave: 8
  - Done when: `python -c "import json; json.load(open('packages/loop_link/examples/geoviewer_link.ipynb'))"`
    exits 0. A person runs it against GeoViewer (manual).

## Phase E: MCP server (user story 6)

- [ ] T060 [Test] [M] Write the MCP server tests (D7).
  - Do: `pytest.importorskip("mcp")`. Test the pure functions:
    `build_tools(commands)` makes one tool for each command with
    `tool_available = true`, with the name `object_set_visible` for
    `object.set_visible` and the input schema of the viewer; the screenshot
    handler gives an image content with `mimeType` `image/png`; a
    `ViewerError` becomes a tool error with the code and the text.
  - Do: Use the fake viewer of T032 for the handlers.
  - Files: `packages/loop_link/tests/test_mcp.py`
  - Needs: T032
  - Wave: 3
  - Done when: the tests run and fail (or skip when `mcp` is not
    installed; then install the extra and see them fail).
- [ ] T061 [Core] [M] Write the MCP server (D7).
  - Do: `loop_link/mcp/__init__.py` (no import of `mcp` at package import
    time outside this folder), `server.py`, `__main__.py` (stdio). Tools:
    each command, plus `screenshot`, `pick` and `list_objects`.
  - Files: `packages/loop_link/src/loop_link/mcp/__init__.py`, `packages/loop_link/src/loop_link/mcp/server.py`, `packages/loop_link/src/loop_link/mcp/__main__.py`
  - Needs: T036, T060
  - Wave: 6
  - Done when: the tests of T060 pass, and `python -c "import loop_link"`
    does not import `mcp` (check `sys.modules`).

## Phase Z: Finish (docs, CI, end to end, checks)

- [ ] T070 [Docs] [S] Update the README of `loop_link`.
  - Do: Sections: install (numpy only; extras `mcp`), `connect()` and the
    token, send `loop_common` objects with `to_message`, the tool session
    (commands, screenshot, pick), `GeoViewerView` (a pointer to
    `loopstructural_visualisation`), the MCP server
    (`claude mcp add geoviewer -- python -m loop_link.mcp`). ASD-STE100.
  - Files: `packages/loop_link/README.md`
  - Needs: T053, T061
  - Wave: 8
  - Done when: each code example in the README runs against the fake viewer
    or a real viewer (manual check is enough).
- [ ] T071 [Setup] [M] Add the numpy-only CI job (SC-003).
  - Do: A new job in `packages.yml`: `pip install numpy pytest` and
    `pip install --no-deps ./packages/loop_link`, then
    `pytest packages/loop_link/tests -m minimal`. One OS and the lowest
    Python version is enough.
  - Do: Check that each test file that needs numpy only has the `minimal`
    marker, and that no `minimal` test imports `loop_common`, PIL or `mcp`.
  - Files: `.github/workflows/packages.yml`
  - Needs: T011, T012, T021, T023, T030, T033, T035, T061
  - Wave: 9
  - Done when: the same commands pass in a new virtual environment on the
    local machine.
- [ ] T072 [Docs] [S] Add a ROADMAP entry.
  - Do: One entry: `loop_link` (GeoViewer link), `GeoViewerView`, and the
    GeoViewer gaps OP1, OP2, OP6.
  - Files: `ROADMAP.md`
  - Needs: T053
  - Wave: 8
  - Done when: the entry is there and names `specs/003-geoviewer-link`.
- [ ] T073 [Test] [M] Write the end-to-end test against a real GeoViewer (SC-001, SC-006).
  - Do: Marker `geoviewer`. Skip when the environment variable
    `GEOVIEWER_HEADLESS` (path to `geoviewer-headless`) is not set.
  - Do: Start `geoviewer-headless --port 0` with `GEOVIEWER_TOKEN` set to a
    random token. Read the port from its line `the link listens on port N`.
    Stop the process at the end.
  - Do: Send one object of each type of FR-003 with one property. Check that
    the viewer sends no `error`. Check `scene.inventory` on a second session.
  - Do: Send a point 500 km from the origin. `pick_ray` straight down onto it
    and check that the hit position is within 1 mm (SC-006).
  - Do: Run `colour.set_active` and a screenshot. If the screenshot gives
    `no_gpu`, skip that part.
  - Files: `packages/loop_link/tests/test_e2e_geoviewer.py`
  - Needs: T024, T036
  - Wave: 7
  - Done when: the test passes with `GEOVIEWER_HEADLESS` set to
    `D:/cargo-target/debug/geoviewer-headless.exe` (or a newer build), and is
    skipped without it.
- [ ] T074 [Check] [M] Run all checks and update the spec status.
  - Do: Run the "Before done" commands of the orchestrator notes. Fix the
    failures.
  - Do: Set the spec status to `Implemented (phases A to E)` and list what is
    open (phase F, manual checks of T055 and T070).
  - Files: `specs/003-geoviewer-link/spec.md`, `specs/003-geoviewer-link/tasks.md`
  - Needs: T055, T070, T071, T072, T073
  - Wave: 10
  - Done when: all commands pass.

## Phase F: Selection (user story 7, waits for a GeoViewer spec)

All tasks of this phase are **Blocked by OP6**. Plan D9 lists what the
GeoViewer spec must give. Write the names of the GeoViewer messages from that
spec into these tasks before you start.

- [ ] T080 [Test] [M] Write the tests for `ToolSession.selection()`. Blocked by OP6.
  - Do: Add `selection.get` to the fake viewer. Check the parse into
    `Selection` with `int64` indices, the `truncated` flag and an empty
    selection.
  - Files: `packages/loop_link/tests/test_selection.py`, `packages/loop_link/tests/geoviewer_fake_server.py`
  - Needs: T036
  - Wave: 11
  - Done when: the tests run and fail.
- [ ] T081 [Test] [M] Write the tests for `wait_for_click()` and `watch()`. Blocked by OP6.
  - Do: Add `events.subscribe`, `selection.changed` and `pick` events to the
    fake viewer. Check that `wait_for_click` gives the hit, that `watch`
    calls the callback within 0.5 s, and that `stop()` ends the thread.
  - Files: `packages/loop_link/tests/test_events.py`
  - Needs: T080
  - Wave: 12
  - Done when: the tests run and fail.
- [ ] T082 [Core] [M] Write selection, click and watch (D9). Blocked by OP6.
  - Files: `packages/loop_link/src/loop_link/geoviewer/tool.py`, `packages/loop_link/src/loop_link/geoviewer/link.py`, `packages/loop_link/src/loop_link/geoviewer/__init__.py`
  - Needs: T080, T081
  - Wave: 13
  - Done when: the tests of T080 and T081 pass.
- [ ] T083 [Test] [M] Test `GeoViewerView.selection()`. Blocked by OP6.
  - Do: Check that a selection of object ids maps back to the feature, the
    `loop_common` object and the indices, and that
    `obj.properties[name][indices]` gives the selected values.
  - Files: `packages/loopstructural_visualisation/tests/test_geoviewer_selection.py`
  - Needs: T053, T080
  - Wave: 12
  - Done when: the test runs and fails.
- [ ] T084 [Core] [M] Write `GeoViewerView.selection()`. Blocked by OP6.
  - Files: `packages/loopstructural_visualisation/src/loopstructuralvisualisation/_geoviewer_view.py`
  - Needs: T082, T083
  - Wave: 14
  - Done when: the test of T083 passes.
- [ ] T085 [Test] [M] Add selection to the end-to-end test. Blocked by OP6.
  - Do: Use `selection.set` (from the GeoViewer spec), then `selection()`,
    and compare.
  - Files: `packages/loop_link/tests/test_e2e_geoviewer.py`
  - Needs: T073, T082
  - Wave: 14
  - Done when: the test passes against a GeoViewer build that has the
    selection spec.

## Dependencies

- T001 comes first. It decides the state of the branch.
- Phase A: the fixture tests (T011) and the data array tests (T012) come
  before the protocol code (T013, T014). T013 and T014 edit the same file, so
  they run one after the other. The `loop_common` import fix (T015, T016) is
  independent.
- Phase B: the shapes (T020) come before the adapter tests (T021). The
  adapters (T024) need the message functions (T014). T024 also edits
  `geoviewer/__init__.py`, so it runs after T036.
- Phase C: the fake viewer (T032) comes before the tool, view and MCP tests.
  Discovery (T031) and the tool session (T036) both edit `geoviewer/link.py`
  and `__init__.py`, so T036 runs after T031.
- Phase D needs the adapters and the tool session.
- Phase E needs the tool session only. It runs at the same time as phase D.
- Phase Z needs phases A to E.
- Phase F needs a GeoViewer spec (OP6).

## Wave table

| Wave | Tasks | Tier [S] | Tier [M] |
|---|---|---|---|
| 1 | T001 | 0 | 1 |
| 2 | T002, T003, T010, T015, T020, T032, T050 | 5 | 2 |
| 3 | T011, T012, T016, T021, T022, T023, T030, T033, T035, T051, T052, T060 | 3 | 9 |
| 4 | T013, T031, T034 | 1 | 2 |
| 5 | T014, T036 | 0 | 2 |
| 6 | T024, T061 | 0 | 2 |
| 7 | T053, T073 | 0 | 2 |
| 8 | T055, T070, T072 | 2 | 1 |
| 9 | T071 | 0 | 1 |
| 10 | T074 | 0 | 1 |
| 11 | T080 (blocked) | 0 | 1 |
| 12 | T081, T083 (blocked) | 0 | 2 |
| 13 | T082 (blocked) | 0 | 1 |
| 14 | T084, T085 (blocked) | 0 | 2 |

## Critical path

T001 -> T010 -> T011 -> T013 -> T014 -> T024 -> T053 -> T070 -> T071 -> T074

(10 tasks long. It sets the minimum time.)

## Coverage of the spec

| Requirement | Tasks |
|---|---|
| Story 1, FR-008, FR-009, SC-004 | T050, T051, T052, T053, T055 |
| Story 2, FR-005, SC-005 | T030, T031 |
| Story 3, FR-002, FR-003, FR-004 | T011 to T014, T020 to T024 |
| Story 4, FR-006, FR-007 | T032 to T036 |
| Story 5, FR-001, SC-003 | T003, T021 (minimal case), T071 |
| Story 6, FR-011 | T060, T061, T070 |
| Story 7, FR-013 | T080 to T085 (blocked by OP6) |
| FR-010, SC-002 | T010, T011 |
| FR-012 | T015, T016 |
| SC-001, SC-006 | T073 |
| Edge cases: frame too large, wrong length, NaN | T012, T014 |
| Edge case: viewer origin wins | existing `push` (kept), T073 |
| Edge case: `busy` from a second data client | T032, T035, T036 |
