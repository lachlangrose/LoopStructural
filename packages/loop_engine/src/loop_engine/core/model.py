from .linker import ObservationLinker
from .state import ModelState
from ..tasks.base import Task


class Model:
    def __init__(self, schema, grid=None):
        self.schema = schema
        self.grid = grid
        self.current_state = None
        self._linker = ObservationLinker(schema)

    def update_parameter(self, feature_id, new_params):
        """User changes something in the schema."""
        if hasattr(self.schema, "update"):
            self.schema.update(feature_id, new_params)
        # We don't solve yet. We just know the state is now invalid.
        self._invalidate(feature_id)

    def _invalidate(self, feature_id):
        # A minimal invalidation strategy: next solve recomputes dependent tasks.
        del feature_id

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
                result = task.execute(inputs)
                new_state.results[task.id] = result
            else:
                # Reuse result from old state
                new_state.results[task.id] = self.current_state.get_feature(task.id)

        self.current_state = new_state
        return self.current_state

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
