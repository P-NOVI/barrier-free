"""오차 지표와 묶음별 오차."""

import numpy as np

ROUND_DIGITS = 5


def mae(y: np.ndarray, pred: np.ndarray) -> float:
    return float(np.mean(np.abs(y - pred)))


def rmse(y: np.ndarray, pred: np.ndarray) -> float:
    return float(np.sqrt(np.mean((y - pred) ** 2)))


def scores(y: np.ndarray, pred: np.ndarray) -> dict[str, float]:
    return {
        "mae": round(mae(y, pred), ROUND_DIGITS),
        "rmse": round(rmse(y, pred), ROUND_DIGITS),
    }


def improvement(base: float, value: float) -> float:
    """baseline 오차 대비 줄어든 비율(0.1 = 10% 줄었다)."""
    return round((base - value) / base, 4)


def grouped_mae(
    keys: np.ndarray, y: np.ndarray, pred: np.ndarray, base_pred: np.ndarray
) -> dict[str, dict[str, float]]:
    """keys 값마다 행 수, 모델 MAE, baseline MAE."""
    result = {}
    for key in np.unique(keys):
        mask = keys == key
        result[str(key.item() if hasattr(key, "item") else key)] = {
            "rows": int(mask.sum()),
            "model_mae": round(mae(y[mask], pred[mask]), ROUND_DIGITS),
            "baseline_mae": round(mae(y[mask], base_pred[mask]), ROUND_DIGITS),
        }
    return result
