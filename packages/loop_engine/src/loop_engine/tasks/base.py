class Task:
    def __init__(
        self,
        feature_id,
        dependencies=None,
        linked_data=None,
        feature=None,
        interpretation=None,
    ):
        self.id = feature_id
        self.dependencies = dependencies or []
        # Keep a clearer alias for call sites that use graph terminology.
        self.predecessors = list(self.dependencies)
        self.linked_data = linked_data
        self.feature = feature
        self.interpretation = interpretation or {}
        self.is_dirty = True

    def execute(self, dependency_results):
        """Return the minimum payload needed by downstream interpolator builders."""
        return {
            "feature_id": self.id,
            "feature": self.feature,
            "dependencies": self.predecessors,
            "dependency_results": dependency_results,
            "linked_data": self.linked_data,
            "interpretation": self.interpretation,
        }
