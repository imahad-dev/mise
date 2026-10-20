"""Per item, per daypart demand forecast for the next 7 days. Pure: no database, no LLM.

Candidates (see docs/analytics.md):
- seasonal_naive: same weekday last week (y[t-7])
- trailing_4w_mean: mean of the same weekday over the last 4 weeks (available weeks only)
- hgb: scikit-learn HistGradientBoostingRegressor (Poisson loss) on day of week, daypart,
  lag-7, lag-14, 28-day rolling mean (ending t-7) and promo flag, pooled over all series

Backtest: rolling origin over the last 14 days (two 7-day folds). The method with the lowest
WAPE is used for the forecast. With fewer than 14 days of history no backtest is run, the
trailing mean baseline is used and the result is flagged low confidence.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor

HORIZON_DAYS = 7
BACKTEST_DAYS = 14
MIN_HISTORY_DAYS = 14
# Model needs lag-14 plus at least 14 days of training rows before the first backtest origin.
MIN_MODEL_HISTORY_DAYS = BACKTEST_DAYS + 14 + 14
INTERVAL_QUANTILE = 0.8
MODEL_NAME = "HistGradientBoostingRegressor(loss=poisson)"
METHOD_ORDER = ("seasonal_naive", "trailing_4w_mean", "hgb")  # tie-break: simplest first

SeriesKey = tuple[str, str]  # (item_id, daypart)


@dataclass
class ForecastInput:
    start: date  # first day of history
    series: dict[SeriesKey, np.ndarray]  # daily units, index 0 == start, zero-filled
    promo: dict[SeriesKey, np.ndarray]  # 0/1 per day, same shape as series

    @property
    def n_days(self) -> int:
        return len(next(iter(self.series.values()))) if self.series else 0


def build_input(
    rows: list[tuple[str, date, str, float]],
    promos: list[tuple[str, date, date]],
    start: date,
    end: date,
) -> ForecastInput:
    """Zero-filled daily series from (item_id, local_date, daypart, units) rows, start..end."""
    n = (end - start).days + 1
    series: dict[SeriesKey, np.ndarray] = {}
    for item_id, d, daypart, units in rows:
        if start <= d <= end:
            arr = series.setdefault((item_id, daypart), np.zeros(n))
            arr[(d - start).days] += units
    promo = {key: np.zeros(n) for key in series}
    for item_id, p0, p1 in promos:
        for key in promo:
            if key[0] != item_id:
                continue
            for i in range(max(0, (p0 - start).days), min(n, (p1 - start).days + 1)):
                promo[key][i] = 1.0
    return ForecastInput(start=start, series=series, promo=promo)


def _lag(y: np.ndarray, t: int, k: int) -> float:
    return float(y[t - k]) if t - k >= 0 else math.nan


def _rolling_mean_28(y: np.ndarray, t: int) -> float:
    """Mean of the 28 days ending at t-7: the latest window still observed at a 7-day horizon."""
    seg = y[max(0, t - 34) : t - 6] if t - 6 > 0 else y[:0]
    return float(np.mean(seg)) if len(seg) else math.nan


def _fill(pred: float, y: np.ndarray, origin: int) -> float:
    """Cold start: when a lag is missing use the mean of the history before the origin."""
    if not math.isnan(pred):
        return pred
    return float(np.mean(y[:origin])) if origin > 0 else 0.0


def _features(fi: ForecastInput, key: SeriesKey, t: int, promo_value: float) -> list[float]:
    y = fi.series[key]
    dow = (fi.start + timedelta(days=t)).weekday()
    return [
        float(dow),
        1.0 if key[1] == "dinner" else 0.0,
        _lag(y, t, 7),
        _lag(y, t, 14),
        _rolling_mean_28(y, t),
        promo_value,
    ]


def _fit_model(fi: ForecastInput, before: int) -> HistGradientBoostingRegressor | None:
    """Fit on rows t < before that have lag-14 available."""
    xs, ys = [], []
    for key, y in fi.series.items():
        for t in range(14, before):
            xs.append(_features(fi, key, t, float(fi.promo[key][t])))
            ys.append(float(y[t]))
    if len(ys) < 20 or sum(ys) <= 0:
        return None
    model = HistGradientBoostingRegressor(
        loss="poisson",
        learning_rate=0.05,
        max_iter=200,
        max_leaf_nodes=15,
        min_samples_leaf=20,
        categorical_features=[0, 1],
        early_stopping=False,
        random_state=0,
    )
    model.fit(np.asarray(xs), np.asarray(ys))
    return model


def _predict(
    method: str,
    fi: ForecastInput,
    key: SeriesKey,
    targets: list[int],
    origin: int,
    model: HistGradientBoostingRegressor | None,
    promo_future: float | None = None,
) -> list[float]:
    """Predict days `targets` (all < origin + 7) using only data before `origin`."""
    y = fi.series[key]
    if method == "hgb":
        rows = [
            _features(
                fi, key, t, promo_future if promo_future is not None else float(fi.promo[key][t])
            )
            for t in targets
        ]
        return [max(0.0, float(v)) for v in model.predict(np.asarray(rows))]
    # Every lag is >= 7 days, so with targets < origin + 7 no value at or after origin is read.
    assert max(targets) < origin + HORIZON_DAYS
    return [
        _fill(_lag(y, t, 7) if method == "seasonal_naive" else _trailing_mean(y, t), y, origin)
        for t in targets
    ]


def _trailing_mean(y: np.ndarray, t: int) -> float:
    """Mean of the same weekday over the last 4 weeks (weeks available)."""
    vals = [y[t - k] for k in (7, 14, 21, 28) if t - k >= 0]
    return float(np.mean(vals)) if vals else math.nan


def _metrics(actual: list[float], pred: list[float]) -> dict:
    a, p = np.asarray(actual), np.asarray(pred)
    abs_err = np.abs(a - p)
    total = float(a.sum())
    return {
        "wape": round(float(abs_err.sum()) / total, 4) if total > 0 else None,
        "mae": round(float(abs_err.mean()), 4) if len(a) else None,
        "n_points": len(a),
    }


def backtest(fi: ForecastInput) -> dict:
    """Rolling-origin backtest over the last 14 days. Returns metrics and scaled residuals."""
    n = fi.n_days
    origins = [n - BACKTEST_DAYS, n - BACKTEST_DAYS + HORIZON_DAYS]
    methods = ["seasonal_naive", "trailing_4w_mean"]
    if n >= MIN_MODEL_HISTORY_DAYS:
        methods.append("hgb")

    actual: list[float] = []
    preds: dict[str, list[float]] = {m: [] for m in methods}
    for origin in origins:
        targets = list(range(origin, origin + HORIZON_DAYS))
        model = _fit_model(fi, origin) if "hgb" in methods else None
        if "hgb" in methods and model is None:
            methods.remove("hgb")
            preds.pop("hgb")
        for key, y in sorted(fi.series.items()):
            actual.extend(float(y[t]) for t in targets)
            for m in methods:
                preds[m].extend(_predict(m, fi, key, targets, origin, model))

    results = {m: _metrics(actual, preds[m]) for m in methods}
    scored = [m for m in METHOD_ORDER if m in results and results[m]["wape"] is not None]
    best = min(scored, key=lambda m: results[m]["wape"]) if scored else "trailing_4w_mean"
    # Residuals scaled by sqrt(prediction): count noise grows roughly with sqrt of the mean.
    scaled = [abs(a - p) / math.sqrt(max(p, 1.0)) for a, p in zip(actual, preds[best], strict=True)]
    return {
        "methods": results,
        "best": best,
        "q_scaled_residual": float(np.quantile(scaled, INTERVAL_QUANTILE)) if scaled else None,
    }


def forecast(fi: ForecastInput) -> dict:
    """Backtest (when history allows), pick the best method and forecast the next 7 days."""
    n = fi.n_days
    if n == 0 or not fi.series:
        return {
            "method": None,
            "model_name": None,
            "history_days": 0,
            "low_confidence": True,
            "backtest": None,
            "points": [],
        }

    low_confidence = n < MIN_HISTORY_DAYS
    bt = None if low_confidence else backtest(fi)
    method = "trailing_4w_mean" if bt is None else bt["best"]
    model = _fit_model(fi, n) if method == "hgb" else None
    if method == "hgb" and model is None:
        method = "trailing_4w_mean"

    targets = list(range(n, n + HORIZON_DAYS))
    points = []
    for key in sorted(fi.series):
        preds = _predict(method, fi, key, targets, n, model, promo_future=0.0)
        for t, p in zip(targets, preds, strict=True):
            scale = math.sqrt(max(p, 1.0))
            # Without a backtest fall back to a Poisson-style ±1.28·sqrt(mean) band.
            half = (bt["q_scaled_residual"] if bt and bt["q_scaled_residual"] else 1.28) * scale
            points.append(
                {
                    "date": (fi.start + timedelta(days=t)).isoformat(),
                    "item_id": key[0],
                    "daypart": key[1],
                    "forecast": round(p, 2),
                    "lo": round(max(0.0, p - half), 2),
                    "hi": round(p + half, 2),
                }
            )

    return {
        "method": method,
        "model_name": MODEL_NAME if method == "hgb" else method,
        "history_days": n,
        "low_confidence": low_confidence,
        "backtest": None if bt is None else {"methods": bt["methods"], "best": bt["best"]},
        "points": points,
    }
