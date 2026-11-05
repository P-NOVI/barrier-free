import numpy as np

from foot_traffic import baseline, data, metrics, predict, train

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
        "foot_traffic": np.zeros(3, dtype=np.float32),
    }
    vocab = {"sensor_code": [10, 20, 30]}
    matrix, names = data.build_features(columns, vocab, CONFIG, ["base", "weather"])
    assert names == ["sensor_code", "hour_of_day", "temp_bin", "rain_grade"]
    # 센서 30 → 2번째(0부터), 10 → 0, 모르는 99 → -1
    assert matrix[:, 0].tolist() == [2, 0, data.UNKNOWN_CATEGORY]
    assert matrix[:2, 2].tolist() == [1, -1]
    assert matrix[:2, 3].tolist() == [0, 2]


def test_off_adjacent_flags() -> None:
    # 평일, 쉬는 날, 평일, 쉬는 날 2일, 평일 2일
    off = np.array([False, True, False, True, True, False, False])
    before, after = data.off_adjacent_flags(off)
    assert before.tolist() == [True, False, True, False, False, False, False]
    assert after.tolist() == [False, False, True, False, False, True, False]


def test_add_off_adjacent_maps_rows_to_days(tmp_path) -> None:
    import pyarrow as pa
    import pyarrow.parquet as pq

    days = np.arange("2026-10-01", "2026-10-08", dtype="datetime64[D]")
    off = [False, True, True, False, False, False, True]
    path = tmp_path / "daily.parquet"
    pq.write_table(
        pa.table({"date": pa.array(days, type=pa.date32()), "is_off_day": off}), path
    )
    columns = {
        "slot_start": np.array(
            ["2026-10-01T09:00", "2026-10-04T23:00", "2026-10-06T00:00"],
            dtype="datetime64[s]",
        )
    }
    data.add_off_adjacent(columns, path)
    # 10/1 은 다음날이 쉬는 날, 10/4 는 어제가 쉬는 날, 10/6 은 다음날이 쉬는 날
    assert columns["is_before_off_day"].tolist() == [1.0, 0.0, 1.0]
    assert columns["is_after_off_day"].tolist() == [0.0, 1.0, 0.0]


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


RATIO = {"mode": "ratio", "floor": 1.0, "weight": "ref"}


def reference_part() -> dict:
    nan = np.nan
    return {
        "foot_traffic": np.zeros(4),
        "level_same_dow_hour": np.array([100.0, nan, nan, 0.2]),
        "level_same_hour": np.array([50.0, 60.0, nan, nan]),
    }


def test_reference_level_prefers_recent_level_then_fallback_with_floor() -> None:
    fallback = np.array([1.0, 1.0, 30.0, 1.0])
    ref = baseline.reference_level(reference_part(), fallback, RATIO)
    # 같은 요일·시각 → 같은 시각 → fallback 순서, 0.2 는 floor 1 로 본다.
    assert ref.tolist() == [100.0, 60.0, 30.0, 1.0]
    nothing = baseline.reference_level(reference_part(), np.full(4, np.nan), RATIO)
    assert np.isnan(nothing[2]) and nothing[0] == 100.0


def test_reference_level_is_one_for_absolute_target() -> None:
    ref = baseline.reference_level(reference_part(), np.ones(4), {"mode": "absolute"})
    assert ref.tolist() == [1.0, 1.0, 1.0, 1.0]


def test_ratio_target_round_trips_to_people() -> None:
    y = np.array([120.0, 45.0, 3000.0])
    ref = np.array([100.0, 60.0, 2500.0])
    assert np.allclose((y / ref) * ref, y)


def test_train_model_accepts_sample_weights() -> None:
    rng = np.random.default_rng(1)
    x = rng.integers(0, 4, size=(400, 1)).astype(np.float32)
    ref = np.where(x[:, 0] >= 2, 500.0, 5.0)
    y = (x[:, 0] / 3).astype(np.float32)
    config = {
        "params": {
            "learning_rate": 0.3,
            "num_leaves": 4,
            "min_data_in_leaf": 5,
            "verbosity": -1,
        },
        "num_boost_round": 30,
        "early_stopping_rounds": 5,
        "seed": 1,
    }
    booster = train.train_model(
        "regression_l1", (x, y, ref), (x, y, ref), ["hour_of_day"], [], config
    )
    pred = train.predict(booster, x)
    # 가중치가 큰 행은 잘 맞추고, 가중치가 작은 행은 덜 맞춘다.
    heavy = ref > 100
    assert metrics.mae(y[heavy], pred[heavy]) < 0.05
    assert metrics.mae(y[~heavy], pred[~heavy]) > metrics.mae(y[heavy], pred[heavy])


def test_pick_reference_uses_validation_mae_of_the_stronger_baseline() -> None:
    base = {
        "median": {"valid": {"mae": 107.8}, "test": {"mae": 90.0}},
        "mean": {"valid": {"mae": 102.0}, "test": {"mae": 120.0}},
    }
    # 테스트 값이 아니라 검증 값으로 고른다.
    assert train.pick_reference(base) == "mean"
    base["median"]["valid"]["mae"] = 99.0
    assert train.pick_reference(base) == "median"


def test_error_rate_is_independent_of_sensor_scale() -> None:
    small = metrics.error_rate(np.array([10.0, 20.0]), np.array([12.0, 18.0]))
    large = metrics.error_rate(np.array([1000.0, 2000.0]), np.array([1200.0, 1800.0]))
    assert small == large == 4 / 30
    assert np.isnan(metrics.error_rate(np.zeros(2), np.ones(2)))


def test_grouped_mae() -> None:
    keys = np.array(["a", "a", "b"])
    y = np.array([0.0, 100.0, 100.0])
    pred = np.array([50.0, 50.0, 100.0])
    base = np.array([0.0, 0.0, 0.0])
    got = metrics.grouped_mae(keys, y, pred, base)
    assert got["a"] == {
        "rows": 2,
        "mean_actual": 50.0,
        "model_mae": 50.0,
        "baseline_mae": 50.0,
        "model_error_rate": 1.0,
        "baseline_error_rate": 1.0,
        "model_bias": 0.0,  # (50-0 + 50-100) / 2
        "baseline_bias": -50.0,
    }
    assert got["b"]["model_mae"] == 0.0 and got["b"]["baseline_error_rate"] == 1.0


def test_level_breakdown_splits_by_actual_size_and_reports_bias() -> None:
    y = np.array([50.0, 150.0, 600.0, 1500.0, 3000.0])
    pred = np.array([40.0, 150.0, 500.0, 1400.0, 2700.0])  # 큰 값은 적게 예측
    base = np.array([50.0, 150.0, 600.0, 1500.0, 3000.0])
    got = train.level_breakdown(y, y, pred, base, [0, 100, 1000], top_quantile=0.8)
    assert list(got["bins"]) == ["0~100", "100~1000", "1000+"]
    assert got["bins"]["0~100"]["model_bias"] == -10.0
    assert got["bins"]["1000+"]["rows"] == 2
    assert got["bins"]["1000+"]["model_bias"] == -200.0  # (-100 + -300) / 2
    assert got["bins"]["1000+"]["baseline_bias"] == 0.0
    # 상위 20% 는 가장 큰 값 하나(3000)
    assert got["top"]["rows"] == 1 and got["top"]["model_bias"] == -300.0


def test_level_breakdown_by_prediction_exposes_regression_to_the_mean() -> None:
    # 예측은 항상 정확한 평균(100)이고 실제는 평균 둘레로 흩어진다.
    y = np.array([60.0, 80.0, 100.0, 120.0, 140.0])
    pred = np.full(5, 100.0)
    base = pred.copy()
    by_actual = train.level_breakdown(y, y, pred, base, [0, 110], top_quantile=0.6)
    by_pred = train.level_breakdown(pred, y, pred, base, [0, 110], top_quantile=0.6)
    # 실제 값으로 묶으면 큰 쪽은 적게, 작은 쪽은 많이 예측한 것처럼 보인다.
    assert (
        by_actual["bins"]["110+"]["model_bias"]
        < 0
        < by_actual["bins"]["0~110"]["model_bias"]
    )
    # 예측 값으로 묶으면 편향이 없다.
    assert by_pred["bins"]["0~110"]["model_bias"] == 0.0


def test_day_type_and_rain_kind() -> None:
    part = {
        "is_holiday": np.array([1, 0, 0], dtype=np.float32),
        "is_off_day": np.array([1, 1, 0], dtype=np.float32),
        "rain_mm": np.array([0.0, 2.0, np.nan], dtype=np.float32),
    }
    assert train.day_type(part).tolist() == ["holiday", "weekend", "weekday"]
    assert train.rain_kind(part).tolist() == ["no_rain", "rain", "unknown"]


def day_part() -> dict:
    hours = np.array([8, 9], dtype=np.int8)
    return {
        "sensor_code": np.array([7, 7], dtype=np.int32),
        "hour_of_day": hours,
        "day_of_week": np.array([4, 4], dtype=np.int8),
        "foot_traffic": np.array([500.0, 620.0], dtype=np.float32),
        "temp": np.array([20.0, 21.0], dtype=np.float32),
        "rain_mm": np.array([0.0, 2.5], dtype=np.float32),
        "is_holiday": np.zeros(2, dtype=np.float32),
        "is_off_day": np.zeros(2, dtype=np.float32),
        "is_before_off_day": np.ones(2, dtype=np.float32),
        "is_after_off_day": np.zeros(2, dtype=np.float32),
    }


def test_select_day_matches_sensor_and_date() -> None:
    columns = {
        "sensor_code": np.array([7, 7, 8], dtype=np.int32),
        "slot_start": np.array(
            ["2026-10-10T08:00", "2026-10-11T08:00", "2026-10-10T08:00"],
            dtype="datetime64[s]",
        ),
    }
    assert predict.select_day(columns, 7, "2026-10-10").tolist() == [True, False, False]


def test_day_tags_and_table() -> None:
    part = day_part()
    assert predict.day_tags(part) == "쉬는 날 전날"
    model = np.array([430.0, 700.0])
    base = np.array([300.0, 310.0])
    table = predict.format_table(part, model, base, None)
    assert "8시" in table and "500" in table and "430" in table and "2.5" in table
    assert "가정" in predict.format_table(part, model, base, model)


def test_plot_day_writes_png(tmp_path) -> None:
    out = tmp_path / "day.png"
    part = day_part()
    model = np.array([430.0, 700.0])
    predict.plot_day(out, "제목", part, model, model, model, "가정")
    assert out.stat().st_size > 0


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
        "regression_l2", (x, y, None), (x, y, None), ["hour_of_day"], [], config
    )
    pred = train.predict(booster, x)
    assert metrics.mae(y, pred) < 0.05
    assert pred.min() >= 0.0
