class Task:
    def __init__(self, feature_id, dependencies):
        self.id = feature_id
        self.dependencies = dependencies
        self.is_dirty = True

    def execute(self, dependency_results):
        # This calls your 'interpolation' module
        # and returns a 'GeologicalFeature'
        pass
