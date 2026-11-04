"""오차 지표와 묶음별 오차. 유동인구는 명/시간이라 MAE·RMSE 도 사람 수다."""

import numpy as np

ROUND_DIGITS = 5


def mae(y: np.ndarray, pred: np.ndarray) -> float:
    return float(np.mean(np.abs(y - pred)))


def rmse(y: np.ndarray, pred: np.ndarray) -> float:
    return float(np.sqrt(np.mean((y - pred) ** 2)))


def error_rate(y: np.ndarray, pred: np.ndarray) -> float:
    """오차 합 / 실제 합. 센서마다 유동인구 규모가 달라 규모와 무관하게 비교한다."""
    total = float(np.sum(np.abs(y)))
    return float(np.sum(np.abs(y - pred)) / total) if total > 0 else float("nan")


def scores(y: np.ndarray, pred: np.ndarray) -> dict[str, float]:
    return {
        "mae": round(mae(y, pred), ROUND_DIGITS),
        "rmse": round(rmse(y, pred), ROUND_DIGITS),
        "error_rate": round(error_rate(y, pred), ROUND_DIGITS),
    }


def improvement(base: float, value: float) -> float:
    """baseline 오차 대비 줄어든 비율(0.1 = 10% 줄었다)."""
    return round((base - value) / base, 4)


def grouped_mae(
    keys: np.ndarray, y: np.ndarray, pred: np.ndarray, base_pred: np.ndarray
) -> dict[str, dict[str, float]]:
    """keys 값마다 행 수, 실제 평균, 모델·baseline 의 MAE 와 오차율."""
    result = {}
    for key in np.unique(keys):
        mask = keys == key
        result[str(key.item() if hasattr(key, "item") else key)] = {
            "rows": int(mask.sum()),
            "mean_actual": round(float(np.mean(y[mask])), 2),
            "model_mae": round(mae(y[mask], pred[mask]), ROUND_DIGITS),
            "baseline_mae": round(mae(y[mask], base_pred[mask]), ROUND_DIGITS),
            "model_error_rate": round(error_rate(y[mask], pred[mask]), ROUND_DIGITS),
            "baseline_error_rate": round(
                error_rate(y[mask], base_pred[mask]), ROUND_DIGITS
            ),
        }
    return result
