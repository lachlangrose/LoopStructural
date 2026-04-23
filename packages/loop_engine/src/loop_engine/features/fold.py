class FoldBuilder:
    """Builder for fold features."""

    def __init__(self, model: LoopModel):
        self.model = model

    def build(self, fold: Fold) -> None:
        """Build a fold feature."""
        pass
