"""Historical-scenario CVaR optimization with an explicit reviewed-data gate."""

import math
from datetime import date

import numpy as np


def optimize_reviewed_portfolio(returns, instrument_ids, provenance, max_weight=0.1, confidence=0.95, minimum_mean_return=None):
    if (provenance.get("status") != "reviewed_market_observations"
            or provenance.get("usage_rights_confirmed") is not True
            or not provenance.get("reviewed_by")
            or not provenance.get("source_url", "").startswith("https://")
            or provenance.get("frequency") not in ("daily", "weekly", "monthly")):
        raise ValueError("Reviewed market observations, documented usage rights, source, reviewer, and return frequency are required. Estimated bond spreads cannot be optimized as returns.")
    matrix = np.asarray(returns, dtype=float)
    if matrix.ndim != 2 or matrix.shape[0] < 60 or matrix.shape[1] < 2 or not np.isfinite(matrix).all() or (matrix < -1).any():
        raise ValueError("Provide at least 60 aligned, finite historical return scenarios for at least two instruments.")
    if len(instrument_ids) != matrix.shape[1] or len(set(instrument_ids)) != len(instrument_ids):
        raise ValueError("Unique instrument IDs must match the return matrix columns.")
    as_of = date.fromisoformat(provenance["as_of"])
    dates = [date.fromisoformat(value) for value in provenance["scenario_dates"]]
    if (len(dates) != len(matrix) or dates != sorted(set(dates)) or dates[-1] > as_of or as_of > date.today()):
        raise ValueError("Historical scenario dates must be unique, ordered, aligned, and available as of a nonfuture analysis date.")
    if not math.isfinite(max_weight) or not 0 < max_weight <= 1 or matrix.shape[1] * max_weight < 1 - 1e-10:
        raise ValueError("The allocation cap cannot fund a full portfolio with the supplied instruments.")
    if not math.isfinite(confidence) or not 0 < confidence < 1:
        raise ValueError("CVaR confidence must be finite and between zero and one.")
    if minimum_mean_return is not None and not math.isfinite(minimum_mean_return):
        raise ValueError("The minimum historical mean-return constraint must be finite.")
    import cvxpy as cp

    weights = cp.Variable(matrix.shape[1], nonneg=True)
    threshold = cp.Variable()
    excess = cp.Variable(matrix.shape[0], nonneg=True)
    loss = -matrix @ weights
    constraints = [cp.sum(weights) == 1, weights <= max_weight, excess >= loss - threshold]
    if minimum_mean_return is not None:
        constraints.append(matrix.mean(axis=0) @ weights >= minimum_mean_return)
    objective = threshold + cp.sum(excess) / ((1 - confidence) * matrix.shape[0])
    problem = cp.Problem(cp.Minimize(objective), constraints)
    problem.solve(solver="CLARABEL")
    if problem.status != cp.OPTIMAL or weights.value is None:
        raise ValueError("No accurately solved feasible portfolio satisfies the supplied constraints.")
    solved = np.asarray(weights.value).reshape(-1)
    if not np.isfinite(solved).all() or abs(solved.sum() - 1) > 1e-6 or solved.min() < -1e-7 or solved.max() > max_weight + 1e-6:
        raise ValueError("Solver output failed the budget/allocation verification gate.")
    return {"status": "historical_scenario_solution", "method": "CVXPY CVaR / CLARABEL",
            "weights": dict(zip(instrument_ids, map(float, solved))), "scenario_count": len(matrix),
            "confidence": confidence, "historical_cvar_loss": float(problem.value),
            "mean_historical_return": float(matrix.mean(axis=0) @ solved), "frequency": provenance["frequency"],
            "as_of": provenance["as_of"],
            "limitations": "Historical scenario optimization, not a return forecast, suitability assessment, or trade recommendation. Liquidity, transaction costs, and future distribution shift are not modeled."}