class ModelState:
    def __init__(self, grid):
        self.grid = grid  # The common.StructuredGrid
        self.results = {}  # {feature_id: GeologicalFeature}
        self.version = 0

    def get_feature(self, feature_id):
        return self.results.get(feature_id)
