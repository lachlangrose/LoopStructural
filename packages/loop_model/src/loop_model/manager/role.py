from pydantic import BaseModel
from typing import Literal


class DataRole(BaseModel):
    """Defines how a specific piece of data relates to a feature."""

    obs_uid: str
    role: Literal[
        "basal",  # The bottom contact of a unit
        "top",  # The top contact
        "orientation",  # Strike/Dip measurements
        "trace",  # A map-view line representing the feature
        "hanging_wall",  # Observations on the hanging wall side of a fault
        "footwall",  # Observations on the footwall side of a fault
        "slip_vector",  # Fault slip direction constraint
        "thickness",  # Isopach/Point measurement of thickness
        "inside",  # General 'inside/outside' or 'inequality' constraint
        "outside",  # General 'inside/outside' or 'inequality' constraint
    ]
