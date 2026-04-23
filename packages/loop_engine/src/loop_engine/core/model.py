from .linker import ObservationLinker
from .state import ModelState
from .geological_feature import GeologicalFeature as SolvedGeologicalFeature
from ..features.dispatch import create_default_feature_builder_dispatcher
from ..tasks.base import Task


class Model:
    def __init__(self, schema, grid=None, interpolatortype="FDI", nelements=1000):
        self.schema = schema
        self.grid = grid
        self.interpolatortype = interpolatortype
        self.nelements = nelements
        self.current_state = None
        self._linker = ObservationLinker(schema)
        self._builder_dispatcher = create_default_feature_builder_dispatcher()

    def solve(self):
        """The 'Big Green Button'."""
        # 1. Get the topological sort of tasks from the schema graph
        tasks = self._compile_tasks()

        # 2. Create a new state based on current grid
        new_state = ModelState(self.grid)

        # 3. Execute tasks in order
        for task in tasks:
            if task.is_dirty:
                # Pass previous results as inputs (The Kinematic Chain)
                inputs = [new_state.get_feature(p) for p in task.predecessors]
                payload = task.execute(inputs)
                build_result = self._builder_dispatcher.build(payload, self)
                solved_feature = self._coerce_solved_feature(task.id, build_result)
                if solved_feature is not None:
                    new_state.results[task.id] = solved_feature
                elif build_result is not None:
                    new_state.results[task.id] = build_result
                else:
                    new_state.results[task.id] = payload
            else:
                # Reuse result from old state
                new_state.results[task.id] = self.current_state.get_feature(task.id)

        self.current_state = new_state
        return self.current_state

    def _validate_schema(self):
        if not hasattr(self.schema, "get_execution_order"):
            raise ValueError("Schema must implement get_execution_order() method.")
        if not hasattr(self.schema, "features"):
            raise ValueError("Schema must have a 'features' attribute.")
        if not hasattr(self.schema, "bounding_box"):
            raise ValueError("Schema must have a 'bounding_box' attribute.")

    def _build_and_solve_feature(self, task_payload: dict):
        """Wire an InterpolatorInput payload into an InterpolatorBuilder and solve it.

        Mapping convention
        ------------------
        * ``point_constraints``    (Nx3 xyz)      → value constraints at isovalue 0
        * ``gradient_constraints`` (Nx6 xyz+gxgygz) → normal constraints (orientation vectors)
        * ``tangent_constraints``  (Nx6 xyz+txtytz) → tangent constraints

        Parameters
        ----------
        task_payload : dict
            The dict returned by ``Task.execute()``.

        Returns
        -------
        GeologicalInterpolator | None
            Solved interpolator, or None when no data are present.
        """
        # Backward-compatible shim used by call sites/tests that still invoke this
        # helper directly; the main solve path now dispatches by feature strategy.
        return self._builder_dispatcher.build(task_payload, self)

    def _compile_tasks(self):
        execution_order = self.schema.get_execution_order()
        linked = self._linker.build_inputs_by_feature(execution_order)

        tasks = []
        for feature_id in execution_order:
            predecessors = list(self.schema.dag.predecessors(feature_id))
            tasks.append(
                Task(
                    feature_id=feature_id,
                    dependencies=predecessors,
                    linked_data=linked[feature_id],
                    feature=self.schema.features[feature_id],
                )
            )
        return tasks

    def _require_solved_state(self):
        if self.current_state is None:
            raise RuntimeError("Model has not been solved yet. Call solve() first.")
        return self.current_state

    def _resolve_feature_id(self, feature_id=None, feature_name=None):
        if feature_id is not None:
            return feature_id

        if feature_name is None:
            raise ValueError("Provide either feature_id or feature_name.")

        get_by_name = getattr(self.schema, "get_feature_by_name", None)
        if callable(get_by_name):
            feature = get_by_name(feature_name)
            if feature is not None:
                return feature.uuid

        for candidate_id, feature in getattr(self.schema, "features", {}).items():
            if getattr(feature, "name", None) == feature_name:
                return candidate_id

        raise KeyError(f"Feature '{feature_name}' was not found in schema features.")

    def _feature_name_for_id(self, feature_id):
        schema_feature = getattr(self.schema, "features", {}).get(feature_id)
        if schema_feature is not None:
            return getattr(schema_feature, "name", str(feature_id))
        return str(feature_id)

    def _wrap_representation(self, feature_id, representation):
        if isinstance(representation, SolvedGeologicalFeature):
            return representation
        if representation is None:
            return None
        if not hasattr(representation, "evaluate_value"):
            return None
        return SolvedGeologicalFeature(
            name=self._feature_name_for_id(feature_id),
            representation=representation,
        )

    def _coerce_solved_feature(self, feature_id, solved_result):
        wrapped = self._wrap_representation(feature_id, solved_result)
        if wrapped is not None:
            return wrapped

        if isinstance(solved_result, dict):
            for key in ("geological_feature", "feature_object", "feature_instance", "result"):
                candidate = solved_result.get(key)
                wrapped = self._wrap_representation(feature_id, candidate)
                if wrapped is not None:
                    return wrapped

            representation = solved_result.get("representation")
            schema_feature = solved_result.get("feature")
            if representation is not None and hasattr(representation, "evaluate_value"):
                name = getattr(schema_feature, "name", self._feature_name_for_id(feature_id))
                return SolvedGeologicalFeature(name=name, representation=representation)

        return None

    def get_solved_feature(self, feature_id=None, feature_name=None):
        """Return a solved feature object that supports scalar-field evaluation."""
        state = self._require_solved_state()
        resolved_id = self._resolve_feature_id(feature_id=feature_id, feature_name=feature_name)

        solved_result = state.get_feature(resolved_id)
        if solved_result is None:
            raise KeyError(
                f"No solved result is available for feature '{resolved_id}'. "
                "Check the feature id/name and ensure solve() has completed."
            )
        solved_feature = self._coerce_solved_feature(resolved_id, solved_result)
        if solved_feature is None:
            raise TypeError(
                f"Solved result for feature '{resolved_id}' does not expose evaluate_value()."
            )

        return solved_feature

    def evaluate_scalar_field(self, positions, feature_id=None, feature_name=None):
        """Evaluate scalar field values for a solved feature at Nx3 positions."""
        feature = self.get_solved_feature(feature_id=feature_id, feature_name=feature_name)
        return feature.evaluate_value(positions)

    def extract_unit_basal_surface(self, feature_id=None, feature_name=None, value=0.0):
        """Extract the basal isosurface for a solved unit feature.

        By convention the basal contact corresponds to scalar value 0.0 unless
        an alternative threshold is supplied through ``value``.
        """
        feature = self.get_solved_feature(feature_id=feature_id, feature_name=feature_name)
        if not hasattr(feature, "surfaces"):
            resolved_id = self._resolve_feature_id(feature_id=feature_id, feature_name=feature_name)
            raise TypeError(
                f"Solved result for feature '{resolved_id}' does not expose surfaces(value)."
            )
        return feature.surfaces(value)
