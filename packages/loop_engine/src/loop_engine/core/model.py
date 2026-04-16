from .state import ModelState


class Model:
    def __init__(self, schema):
        self.schema = schema
        self.current_state = None

    def update_parameter(self, feature_id, new_params):
        """User changes something in the schema."""
        self.schema.update(feature_id, new_params)
        # We don't solve yet. We just know the state is now invalid.
        self._invalidate(feature_id)

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
