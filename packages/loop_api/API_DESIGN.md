# loop_api Design

## Purpose

`loop_api` is a top-level API module that assembles modeling artifacts from external inputs while preserving ownership boundaries:

- `loop_model` owns geological schema and project contracts.
- `loop_engine` owns solve orchestration and interpretation builders.
- `loop_api` owns ingestion, normalization, validation, and assembly wiring.

V1 provides YAML-driven assembly with a stable public API and extension registries.

## Public API

- `from_yaml(path_or_payload, validation_mode="strict")`
- `to_project(path_or_payload, validation_mode="strict")`
- `to_model(path_or_payload, validation_mode="strict")`
- `solve(path_or_payload, validation_mode="strict")`

## YAML Contract (V1)

Top-level keys:

- `metadata`: free-form metadata map.
- `bounding_box`: `origin`, `maximum`, optional `nsteps`.
- `solve`: optional model options (`interpolatortype`, `nelements`, `interpolation_strategy`).
- `observations`: list of named observations.
- `features`: list of geological features (`unit`, `fault`).
- `topology`: list of typed relationships (`overlies`, `faults`, `abuts`, `erode`, `onlap`, `folds`).

Observation payloads support:

- Inline payload (`inline`): observation data embedded in YAML.
- File payload (`file`): linked data file resolved relative to the YAML location.

## Validation Modes

- `strict`: raise on invalid or unresolved configuration.
- `warn`: collect structured diagnostics and continue where safe.

Diagnostics are structured entries with code, message, severity, and context.

## Extensibility

Three registries allow future adapter expansion without changing core APIs:

- Observation adapter registry: maps observation type -> loader callable.
- Feature adapter registry: maps feature type -> assembler callable.
- Relation adapter registry: maps relation type -> edge application callable.

## Boundaries

`loop_api` does not implement geological build semantics. It delegates model solve to `loop_engine.Model` and schema/project ownership to `loop_model`.
