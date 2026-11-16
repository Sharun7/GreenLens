"""Compare documented climate-model periods without inventing asset-loss multipliers."""

import math
from collections import defaultdict
from datetime import date
from statistics import median


def compare_climate_periods(rows, baseline=(1995, 2014), future=(2031, 2050), scenario="ssp245"):
    if scenario not in ("ssp126", "ssp245", "ssp585") or not baseline[0] <= baseline[1] < future[0] <= future[1]:
        raise ValueError("Use documented ordered baseline/future periods and a supported SSP scenario.")
    grouped = defaultdict(dict)
    for row in rows:
        if (row.get("review_status") != "reviewed" or not row.get("reviewed_by")
                or not row.get("source_url", "").startswith("https://")
                or not row.get("dataset") or not row.get("downscaling_method")
                or not row.get("bias_correction") or not row.get("resolution_m")):
            raise ValueError("Climate projections require reviewed source, model/downscaling provenance, resolution and bias-correction metadata.")
        variable = row["variable"]
        value = row["value"]
        if variable not in ("tasmax", "pr") or isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError("Use finite period-average tasmax or precipitation values with explicit units.")
        units = row["units"]
        if variable == "tasmax":
            if units == "K":
                value -= 273.15
            elif units != "degC":
                raise ValueError("Temperature units must be K or degC.")
        else:
            if units == "kg m-2 s-1":
                value *= 86400
            elif units != "mm/day":
                raise ValueError("Precipitation units must be kg m-2 s-1 or mm/day.")
            if value < 0:
                raise ValueError("Precipitation cannot be negative.")
        start, end = date.fromisoformat(row["period_start"]), date.fromisoformat(row["period_end"])
        key = (row["project_id"], row["model"], variable)
        if row["scenario"] == "historical" and (start.year, end.year) == baseline:
            period = "baseline"
        elif row["scenario"] == scenario and (start.year, end.year) == future:
            period = "future"
        else:
            raise ValueError("Each row must match the specified historical or future period and scenario.")
        if (start.month, start.day, end.month, end.day) != (1, 1, 12, 31) or period in grouped[key]:
            raise ValueError("Use one complete period-average record per project, model, variable, and period.")
        grouped[key][period] = value
    if not grouped:
        raise ValueError("No reviewed climate projections were supplied.")
    projects = defaultdict(lambda: defaultdict(list))
    for (project_id, model, variable), values in grouped.items():
        if set(values) != {"baseline", "future"}:
            raise ValueError("Each model needs a matching historical baseline and future projection.")
        projects[project_id][variable].append({"model": model, "delta": values["future"] - values["baseline"]})
    output = {}
    for project_id, variables in projects.items():
        if set(variables) != {"tasmax", "pr"} or any(len(values) < 3 for values in variables.values()):
            raise ValueError("At least three matched models for both temperature and precipitation are required per project.")
        if {item["model"] for item in variables["tasmax"]} != {item["model"] for item in variables["pr"]}:
            raise ValueError("Use the same model ensemble for both variables.")
        output[project_id] = {}
        for variable, values in variables.items():
            deltas = [item["delta"] for item in values]
            output[project_id][variable] = {"model_count": len(values), "median_delta": median(deltas),
                                           "model_range": [min(deltas), max(deltas)],
                                           "units": "degC" if variable == "tasmax" else "mm/day"}
    return {"status": "documented_period_comparison", "scenario": scenario, "projects": output,
            "limitation": "Model range is not a calibrated confidence interval. Climate-grid projections do not resolve project damage or translate automatically to credit losses."}