"""Translate independent expert evidence without interpreting vector length as slip."""

import numpy as np


def compile_constraints(config, card):
    case = config["case"]
    result = {
        "case": case,
        "free_parameters": ["D_m", "pitch_radians"],
        "fixed": {"fault_geometry": "vertical plane x=0"},
        "pitch_bounds": [-np.pi, np.pi],
        "source": "map-only",
        "confidence": "declared experimental assumption",
        "event": "net F1",
    }
    if case != "E0":
        direction = np.asarray(card["E1"]["slip_direction"], dtype=float)
        if direction.shape != (3,) or not np.isfinite(direction).all():
            raise ValueError("E1 requires a finite 3-vector")
        length = np.linalg.norm(direction)
        if length <= 0 or abs(direction[0]) > 1e-10 * length:
            raise ValueError("Expert direction is zero or outside the fixed fault plane")
        unit = direction / length
        pitch = float(np.arctan2(-unit[2], unit[1]))
        result["source"] = card["E1"]["source"]
        if case == "E1":
            result["fixed"]["direction_unit"] = unit.tolist()
            result["fixed"]["pitch_radians"] = pitch
            result["free_parameters"] = ["D_m"]
        else:
            width = float(config["constraints"]["pitch_half_width_degrees"])
            if not 0 < width < 90 or abs(pitch) + np.deg2rad(width) >= np.pi:
                raise ValueError("Invalid bounded-pitch support")
            result["pitch_bounds"] = [pitch - np.deg2rad(width), pitch + np.deg2rad(width)]
            result["source"] += "; +/-5 degree support is an experimental assumption"
    if card["E0"]["amplitude_prior_m"] != config["prior"]["D_m"]:
        raise ValueError("Contradictory hard amplitude constraints")
    if "D_m" in config.get("constraints", {}):
        raise ValueError("No independent displacement observation is declared")
    return result
