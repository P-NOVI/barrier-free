import numpy as np

from congestion import baseline, data, metrics, train

CONFIG = {
    "temp_bin_c": 5,
    "rain_bins_mm": [0, 1, 5, 20],
    "groups": {
        "base": ["sensor_code", "hour_of_day"],
        "weather": ["temp_bin", "rain_grade"],
        "holiday": ["is_holiday"],
    },
}


def test_rain_grade_boundaries_and_missing() -> None:
    rain = np.array([0.0, 0.5, 1.0, 1.1, 5.0, 20.0, 20.1, np.nan], dtype=np.float32)
    got = data.rain_grade(rain, CONFIG["rain_bins_mm"])
    assert got[:-1].tolist() == [0, 1, 1, 2, 2, 3, 4]
    assert np.isnan(got[-1])


def test_temp_bin_floors_toward_cold() -> None:
    temp = np.array([-0.1, 0.0, 4.9, 5.0, np.nan], dtype=np.float32)
    got = data.temp_bin(temp, 5)
    assert got[:-1].tolist() == [-1, 0, 0, 1]
    assert np.isnan(got[-1])


def test_split_masks_include_test_end_day() -> None:
    slots = np.array(
        [
            "2026-05-31T23:00",
            "2026-06-01T00:00",
            "2026-07-31T23:00",
            "2026-08-01T00:00",
            "2026-10-25T23:00",
            "2026-10-26T00:00",
        ],
        dtype="datetime64[s]",
    )
    split = {
        "valid_start": "2026-06-01",
        "test_start": "2026-08-01",
        "test_end": "2026-10-25",
    }
    masks = data.split_masks(slots, split)
    assert masks["train"].tolist() == [True, False, False, False, False, False]
    assert masks["valid"].tolist() == [False, True, True, False, False, False]
    assert masks["test"].tolist() == [False, False, False, True, True, False]


def test_build_features_maps_categories_and_selects_groups() -> None:
    columns = {
        "sensor_code": np.array([30, 10, 99], dtype=np.int32),
        "hour_of_day": np.array([1, 2, 3], dtype=np.int8),
        "temp": np.array([7.0, -2.0, np.nan], dtype=np.float32),
        "rain_mm": np.array([0.0, 3.0, 0.0], dtype=np.float32),
        "is_holiday": np.array([0, 1, 0], dtype=np.float32),
        "congestion": np.zeros(3, dtype=np.float32),
    }
    vocab = {"sensor_code": [10, 20, 30]}
    matrix, names = data.build_features(columns, vocab, CONFIG, ["base", "weather"])
    assert names == ["sensor_code", "hour_of_day", "temp_bin", "rain_grade"]
    # 센서 30 → 2번째(0부터), 10 → 0, 모르는 99 → -1
    assert matrix[:, 0].tolist() == [2, 0, data.UNKNOWN_CATEGORY]
    assert matrix[:2, 2].tolist() == [1, -1]
    assert matrix[:2, 3].tolist() == [0, 2]


def test_baseline_median_with_sensor_fallback() -> None:
    sensors = np.array([1, 1, 1, 2], dtype=np.int32)
    dow = np.array([0, 0, 0, 0], dtype=np.int8)
    hour = np.array([8, 8, 8, 9], dtype=np.int8)
    y = np.array([0.2, 0.4, 1.0, 0.6], dtype=np.float32)
    keys = baseline.slot_keys(sensors, dow, hour)
    by_slot, by_sensor = baseline.fit_baseline(keys, sensors, y, "median")
    assert by_slot[int(keys[0])] == np.float32(0.4)
    # 센서 1 의 다른 시각은 센서 1 전체 중앙값, 모르는 센서는 0
    new_keys = baseline.slot_keys(
        np.array([1, 3], dtype=np.int32),
        np.array([2, 0], dtype=np.int8),
        np.array([5, 5], dtype=np.int8),
    )
    pred = baseline.predict_baseline(
        new_keys, np.array([1, 3], dtype=np.int32), by_slot, by_sensor
    )
    assert pred.tolist() == [np.float32(0.4), 0.0]


def test_metrics() -> None:
    y = np.array([0.0, 1.0])
    pred = np.array([0.5, 0.5])
    assert metrics.mae(y, pred) == 0.5
    assert metrics.rmse(y, pred) == 0.5
    assert metrics.improvement(0.2, 0.15) == 0.25


def test_grouped_mae() -> None:
    keys = np.array(["a", "a", "b"])
    y = np.array([0.0, 1.0, 1.0])
    pred = np.array([0.5, 0.5, 1.0])
    base = np.array([0.0, 0.0, 0.0])
    got = metrics.grouped_mae(keys, y, pred, base)
    assert got["a"] == {"rows": 2, "model_mae": 0.5, "baseline_mae": 0.5}
    assert got["b"] == {"rows": 1, "model_mae": 0.0, "baseline_mae": 1.0}


def test_day_type_and_rain_kind() -> None:
    part = {
        "is_holiday": np.array([1, 0, 0], dtype=np.float32),
        "is_off_day": np.array([1, 1, 0], dtype=np.float32),
        "rain_mm": np.array([0.0, 2.0, np.nan], dtype=np.float32),
    }
    assert train.day_type(part).tolist() == ["holiday", "weekend", "weekday"]
    assert train.rain_kind(part).tolist() == ["no_rain", "rain", "unknown"]


def test_train_model_learns_simple_pattern() -> None:
    rng = np.random.default_rng(0)
    x = rng.integers(0, 4, size=(400, 1)).astype(np.float32)
    y = (x[:, 0] / 3).astype(np.float32)
    config = {
        "params": {
            "learning_rate": 0.3,
            "num_leaves": 4,
            "min_data_in_leaf": 5,
            "verbosity": -1,
        },
        "num_boost_round": 50,
        "early_stopping_rounds": 5,
        "seed": 1,
    }
    booster = train.train_model(
        "regression_l2", (x, y), (x, y), ["hour_of_day"], [], config
    )
    pred = train.predict(booster, x)
    assert metrics.mae(y, pred) < 0.05
    assert pred.min() >= 0.0 and pred.max() <= 1.0
