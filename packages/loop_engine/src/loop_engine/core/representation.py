class ModelRepresentation:
    def __init__(self, model):
        self.model = model
        self.bounding_box = model.schema.bounding_box
        self.grid = self.bounding_box.structured_grid()

    def _initialise_representation(self):
        if not self.model.is_solved:
            return
        for feature in self.model.features:
            pass

    def get_basal_surface(self, unit_name):
        pass

    def get_fault_surface(self, fault_name):
        pass

    def get_top_surface(self, unit_name):
        pass

    def get_unit_volume(self, unit_name):
        pass

    def get_units(self):
        return self.model.schema.get_units()
