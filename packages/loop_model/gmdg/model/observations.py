from __future__ import annotations

from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field

from .common import Id, UncertaintySpec


class GeologicalObservationSet(BaseModel):
    id: Id
    kind: Literal["on_contact", "below_contact", "above_contact", "tangent", "normal", "gradient"]
    target: Id
    uri: Optional[str] = None
    data: Any = None
    columns: Dict[str, str] = Field(default_factory=dict)
    uncertainty: Optional[UncertaintySpec] = None
    weight: float = 1.0
    region: Optional[Id] = None
    count: Optional[int] = None
    meta: Dict[str, Any] = Field(default_factory=dict)

    def get_array(self):
        if self.data is not None:
            return self.data
        if self.uri:
            try:
                import os

                import numpy as np
                import xarray as xr

                ext = os.path.splitext(self.uri)[1].lower()
                if ext in {".npy"}:
                    self.data = np.load(self.uri)
                elif ext in {".nc", ".netcdf"}:
                    self.data = xr.open_dataset(self.uri)
                elif ext in {".csv"}:
                    try:
                        import pandas as pd
                    except ImportError as e:
                        raise RuntimeError(
                            "Loading CSV observations requires pandas. Install with: pip install pandas"
                        ) from e
                    self.data = pd.read_csv(self.uri)
                elif ext in {".parquet", ".pq"}:
                    try:
                        import pandas as pd
                    except ImportError as e:
                        raise RuntimeError(
                            "Loading Parquet observations requires pandas (and pyarrow/fastparquet). "
                            "Install with: pip install pandas pyarrow"
                        ) from e
                    self.data = pd.read_parquet(self.uri)
                else:
                    raise NotImplementedError(f"Unsupported file extension: {ext}")
                return self.data
            except Exception as e:
                raise RuntimeError(f"Failed to load observation data from {self.uri}: {e}")
        raise ValueError("No observation data available (neither in-memory nor file-based)")
