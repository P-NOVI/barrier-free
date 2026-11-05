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
    """keys 값마다 행 수, 실제 평균, 모델·baseline 의 MAE·오차율·편향."""
    return {
        str(key.item() if hasattr(key, "item") else key): summarize_rows(
            y[keys == key], pred[keys == key], base_pred[keys == key]
        )
        for key in np.unique(keys)
    }


def bias(y: np.ndarray, pred: np.ndarray) -> float:
    """예측 - 실제 평균(명/시간). 음수면 적게 예측하는 쪽으로 치우쳤다."""
    return float(np.mean(pred - y))


def summarize_rows(
    y: np.ndarray, pred: np.ndarray, base_pred: np.ndarray
) -> dict[str, float]:
    """한 묶음의 행 수, 실제 평균, 모델·baseline 의 MAE·오차율·편향."""
    return {
        "rows": int(y.size),
        "mean_actual": round(float(np.mean(y)), 2),
        "model_mae": round(mae(y, pred), ROUND_DIGITS),
        "baseline_mae": round(mae(y, base_pred), ROUND_DIGITS),
        "model_error_rate": round(error_rate(y, pred), ROUND_DIGITS),
        "baseline_error_rate": round(error_rate(y, base_pred), ROUND_DIGITS),
        "model_bias": round(bias(y, pred), 2),
        "baseline_bias": round(bias(y, base_pred), 2),
    }
