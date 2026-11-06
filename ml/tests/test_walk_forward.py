import copy
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from foot_traffic import level_break, recent, walk_forward
from foot_traffic.common import load_config
from foot_traffic.data import add_vacation

DAY = np.timedelta64(1, "D")
START = np.datetime64("2025-01-01")
DAYS = 220
HOURS = (8, 12, 18)
LEVELS = {1: 100.0, 2: 300.0, 3: 1000.0}
EVAL_START = np.datetime64("2025-06-02")  # 월요일
EVAL_END = EVAL_START + 7 * DAY
AS_OF = EVAL_START - 7 * DAY


def make_columns(extra_sensor_in_eval: bool = False) -> dict:
    """센서 3개가 매일 3개 시각에 한 행씩. 값은 센서 규모 × 시각 모양 × 잡음이다."""
    rng = np.random.default_rng(0)
    rows = []
    for sensor, level in LEVELS.items():
        for day in range(DAYS):
            for hour in HOURS:
                shape = {8: 0.6, 12: 1.0, 18: 1.4}[hour]
                rows.append((sensor, day, hour, level * shape * rng.normal(1, 0.05)))
    if extra_sensor_in_eval:  # 학습 구간에는 없고 평가 구간에만 있는 센서
        for day in range(
            (EVAL_START - START).astype(int), (EVAL_END - START).astype(int)
        ):
            for hour in HOURS:
                rows.append((9, day, hour, 500.0))
    n = len(rows)
    sensor = np.array([r[0] for r in rows], dtype=np.int32)
    day = np.array([r[1] for r in rows])
    hour = np.array([r[2] for r in rows], dtype=np.int8)
    slot = (START + day * DAY).astype("datetime64[s]") + hour.astype("timedelta64[h]")
    zeros = np.zeros(n, dtype=np.float32)
    return {
        "sensor_code": sensor,
        "district": np.array([f"D{s}" for s in sensor], dtype=object),
        "slot_start": slot,
        "day_of_week": ((slot.astype("datetime64[D]").astype(np.int64) + 3) % 7).astype(
            np.int8
        ),
        "hour_of_day": hour,
        "lon": np.full(n, 127.0, dtype=np.float32),
        "lat": np.full(n, 37.5, dtype=np.float32),
        "temp": np.full(n, 15.0, dtype=np.float32),
        "rain_mm": zeros.copy(),
        "foot_traffic": np.array([r[3] for r in rows], dtype=np.float32),
        "is_holiday": zeros.copy(),
        "is_off_day": zeros.copy(),
        "off_run_length": zeros.copy(),
        "in_long_holiday": zeros.copy(),
        "days_to_long_holiday": zeros.copy(),
        "days_since_long_holiday": zeros.copy(),
    }


def make_config() -> dict:
    config = load_config()
    config["model"] = {
        **config["model"],
        "num_boost_round": 30,
        "early_stopping_rounds": 3,
        "params": {
            "learning_rate": 0.3,
            "num_leaves": 4,
            "min_data_in_leaf": 5,
            "verbosity": -1,
            "num_threads": 1,
            "deterministic": True,
        },
    }
    config["walk_forward"] = {
        **config["walk_forward"],
        "early_stopping_days": 28,
        "early_stopping": {"method": "smoothed", "max_rounds": 40, "smooth_window": 5},
        "level_break": {
            "break_date": "2025-03-15",
            "before": ["2025-01-01", "2025-03-01"],
            "after": ["2025-04-01", "2025-06-01"],
            "hour_from": 8,
            "hour_to": 18,
            "min_rows": 5,
            "drop_ratio": 0.85,
        },
    }
    return config


@pytest.fixture
def calendar_path(tmp_path: Path) -> Path:
    dates = np.arange(
        START - 30 * DAY, START + (DAYS + 30) * DAY, dtype="datetime64[D]"
    )
    weekend = ((dates.astype(np.int64) + 3) % 7) >= 5
    path = tmp_path / "daily.parquet"
    pq.write_table(
        pa.table({"date": pa.array(dates, type=pa.date32()), "is_off_day": weekend}),
        path,
    )
    return path


def run(columns: dict, calendar_path: Path, rounds: int | None = None) -> dict:
    return walk_forward.run_window(
        columns, AS_OF, EVAL_START, EVAL_END, make_config(), calendar_path, rounds
    )


def test_window_bounds_leave_a_gap_before_evaluation() -> None:
    as_of, start, end = walk_forward.window_bounds("2025-06-02", EVAL_END, 7)
    assert (as_of, start, end) == (AS_OF, EVAL_START, EVAL_END)
    assert start - as_of == 7 * DAY


def test_training_rows_end_before_the_gap_and_evaluation_starts_on_time(
    calendar_path: Path,
) -> None:
    info = run(make_columns(), calendar_path)["info"]
    assert np.datetime64(info["train_last_slot"]) < AS_OF
    assert np.datetime64(info["eval_first_slot"]) >= EVAL_START
    assert np.datetime64(info["eval_last_slot"]) < EVAL_END
    assert info["eval_rows"] == 7 * len(HOURS) * len(LEVELS)
    # as_of 부터 평가 시작 전까지(gap)의 행은 학습에도 평가에도 쓰이지 않는다.
    assert info["train_end"] == str(AS_OF)


def test_changing_evaluation_labels_only_reaches_rows_gap_days_later(
    calendar_path: Path,
) -> None:
    """평가 주 라벨은 학습에 안 쓰이고, 피처로는 gap 일 뒤 행에만 닿는다."""
    gap = walk_forward.recent_config(make_config())["gap_days"]
    columns = make_columns()
    clean = run(columns, calendar_path)
    poisoned = copy.deepcopy(columns)
    slot = poisoned["slot_start"]
    poisoned_day = EVAL_START + DAY
    poisoned["foot_traffic"][(slot >= poisoned_day) & (slot < EVAL_END)] = 1e6
    changed = run(poisoned, calendar_path)
    eval_slot = clean["evaluate"]["slot_start"]
    unaffected = eval_slot < poisoned_day + gap * DAY
    assert unaffected.any() and not unaffected.all()
    np.testing.assert_allclose(
        clean["pred"][unaffected], changed["pred"][unaffected], rtol=1e-9
    )
    np.testing.assert_allclose(
        clean["base"][unaffected], changed["base"][unaffected], rtol=1e-9
    )
    assert clean["info"]["rounds"] == changed["info"]["rounds"]


def test_rows_after_the_evaluation_window_are_never_read(calendar_path: Path) -> None:
    columns = make_columns()
    clean = run(columns, calendar_path)
    poisoned = copy.deepcopy(columns)
    later = poisoned["slot_start"] >= EVAL_END
    poisoned["foot_traffic"][later] = 1e6
    poisoned["temp"][later] = np.nan
    changed = run(poisoned, calendar_path)
    np.testing.assert_allclose(clean["pred"], changed["pred"], rtol=1e-9)
    assert clean["info"] == changed["info"]


def test_categories_and_fallback_stats_come_from_training_rows_only(
    calendar_path: Path,
) -> None:
    result = run(make_columns(extra_sensor_in_eval=True), calendar_path)
    assert result["vocab"]["sensor_code"] == [1, 2, 3]  # 평가에만 있는 센서 9 는 없다
    assert result["info"]["eval_sensors_not_in_train"] == 1
    assert np.all(np.isfinite(result["pred"]))


def test_smoothed_best_iteration_ignores_a_single_dip() -> None:
    # 바닥은 20~25 부근인데 3번째 반복에 우연히 낮은 값이 있다.
    curve = [10.0, 9.0, 1.0] + [8.0 - 0.2 * i for i in range(20)] + [4.0] * 10
    assert int(np.argmin(curve)) + 1 == 3  # 단순 최솟값은 우연한 점을 고른다.
    assert walk_forward.smoothed_best_iteration(curve, window=5) > 10


def test_smoothed_best_iteration_handles_short_curves() -> None:
    assert walk_forward.smoothed_best_iteration([3.0, 2.0, 2.5], window=5) == 2


def test_smoothed_early_stopping_records_a_bounded_iteration(
    calendar_path: Path,
) -> None:
    info = run(make_columns(), calendar_path)["info"]
    stopping = info["early_stopping"]
    assert stopping["method"] == "smoothed"
    assert 1 <= info["rounds"] <= stopping["max_rounds"]
    assert stopping["raw_argmin_iteration"] >= 1
    assert len(stopping["curve_every_10_rounds"]) == stopping["max_rounds"] // 10
    # 내부 검증은 학습 구간의 마지막 28일뿐이고 평가 주 행은 쓰지 않는다.
    assert stopping["inner_validation_days"] == 28
    assert stopping["inner_validation_rows"] > 0


def test_patience_method_still_reproduces_the_first_run(calendar_path: Path) -> None:
    config = make_config()
    config["walk_forward"]["early_stopping"] = {"method": "patience"}
    result = walk_forward.run_window(
        make_columns(), AS_OF, EVAL_START, EVAL_END, config, calendar_path
    )
    assert result["info"]["early_stopping"]["method"] == "patience"
    assert result["info"]["rounds"] >= 1


def test_fixed_rounds_skip_early_stopping(calendar_path: Path) -> None:
    info = run(make_columns(), calendar_path, rounds=7)["info"]
    assert info["rounds"] == 7 and info["early_stopping_best_iteration"] is None


def break_columns() -> dict:
    """센서 1 은 4~6월 낮 시간 평균이 1~2월의 절반이다."""
    columns = make_columns()
    slot = columns["slot_start"]
    after = (slot >= np.datetime64("2025-03-15")) & (columns["sensor_code"] == 1)
    columns["foot_traffic"][after] *= 0.5
    return columns


def test_level_break_is_judged_only_from_data_before_as_of() -> None:
    columns = break_columns()
    config = make_config()["walk_forward"]["level_break"]
    # 이후 구간(4월~)이 시작되기 전 시점에서는 단절이 아직 보이지 않는다.
    assert (
        level_break.flagged_sensors(columns, config, np.datetime64("2025-03-20")) == []
    )
    # 이후 구간에 행이 쌓인 시점에서는 센서 1 이 잡힌다.
    assert level_break.flagged_sensors(
        columns, config, np.datetime64("2025-06-01")
    ) == [1]


def test_level_break_ignores_values_after_as_of() -> None:
    columns = break_columns()
    config = make_config()["walk_forward"]["level_break"]
    as_of = np.datetime64("2025-05-01")
    before = level_break.level_ratios(columns, config, as_of)
    later = columns["slot_start"] >= as_of
    columns["foot_traffic"][later] = 1e6
    assert level_break.level_ratios(columns, config, as_of) == before


def test_keep_after_break_drops_only_flagged_sensors_before_the_break_date() -> None:
    columns = break_columns()
    config = make_config()["walk_forward"]["level_break"]
    keep = level_break.keep_after_break(columns, [1], config)
    old = columns["slot_start"] < np.datetime64("2025-03-15")
    assert not keep[(columns["sensor_code"] == 1) & old].any()
    assert keep[(columns["sensor_code"] == 1) & ~old].all()
    assert keep[columns["sensor_code"] != 1].all()


def break_config(rescale: bool) -> dict:
    config = {
        **make_config()["walk_forward"]["level_break"],
        "transition": ["2025-03-01", "2025-04-01"],
    }
    if rescale:
        config["rescale"] = {
            "hour_from": 12,
            "hour_to": 18,
            "post": ["2025-04-01", "2025-06-01"],
            "min_rows": 5,
        }
    return config


def test_clean_break_drops_transition_and_older_rows_of_flagged_sensors() -> None:
    columns = break_columns()
    keep, scale, stats = level_break.clean_break(
        columns, [1], break_config(False), np.datetime64("2025-06-01")
    )
    sensor1 = columns["sensor_code"] == 1
    early = columns["slot_start"] < np.datetime64("2025-04-01")
    assert scale is None
    assert not keep[sensor1 & early].any()
    assert keep[sensor1 & ~early].all() and keep[~sensor1].all()
    assert stats["rows_dropped"] == int((sensor1 & early).sum())


def test_rescale_matches_old_rows_to_the_new_level_by_hour() -> None:
    columns = break_columns()
    keep, scale, stats = level_break.clean_break(
        columns, [1], break_config(True), np.datetime64("2025-06-01")
    )
    hour = columns["hour_of_day"]
    sensor1 = columns["sensor_code"] == 1
    old = sensor1 & (columns["slot_start"] < np.datetime64("2025-03-01"))
    # 보정 시각(12, 18시)의 단절 전 행은 살리고 약 0.5 를 곱한다. 8시는 뺀다.
    rescaled = old & (hour >= 12)
    assert keep[rescaled].all() and not keep[old & (hour == 8)].any()
    np.testing.assert_allclose(scale[rescaled], 0.5, atol=0.05)
    assert np.all(scale[~rescaled] == 1.0)
    assert stats["rows_rescaled"] == int(rescaled.sum())


def test_rescale_factors_ignore_values_after_as_of() -> None:
    columns = break_columns()
    config = break_config(True)
    as_of = np.datetime64("2025-05-01")
    before = level_break.hour_factors(columns, [1], config, as_of)
    columns["foot_traffic"][columns["slot_start"] >= as_of] = 1e6
    assert level_break.hour_factors(columns, [1], config, as_of) == before


def test_outage_rows_mark_days_whose_daytime_is_all_zero() -> None:
    columns = make_columns()
    day = columns["slot_start"].astype("datetime64[D]")
    sensor1 = columns["sensor_code"] == 1
    columns["foot_traffic"][sensor1 & (day == START + 10 * DAY)] = 0.0
    # 하루 중 한 시각만 0 인 날은 고장으로 보지 않는다.
    partial = sensor1 & (day == START + 11 * DAY) & (columns["hour_of_day"] == 12)
    columns["foot_traffic"][partial] = 0.0
    outage = recent.outage_rows(columns, {"hour_from": 8, "hour_to": 18, "min_rows": 3})
    assert outage.sum() == len(HOURS)
    assert outage[sensor1 & (day == START + 10 * DAY)].all()


def test_outage_days_are_left_out_of_recent_levels() -> None:
    columns = make_columns()
    config = {**walk_forward.recent_config(make_config())}
    day = columns["slot_start"].astype("datetime64[D]")
    zero = (columns["sensor_code"] == 1) & (day == START + 50 * DAY)
    columns["foot_traffic"][zero] = 0.0
    with_zero = recent.recent_levels(columns, config)["level_same_hour"]
    without = recent.recent_levels(columns, config, exclude=zero)["level_same_hour"]
    later = (columns["sensor_code"] == 1) & (day == START + 60 * DAY)
    assert np.all(without[later] > with_zero[later])


def test_extra_levels_use_only_values_gap_days_back() -> None:
    columns = make_columns()
    config = {
        **walk_forward.recent_config(make_config()),
        "extra": {
            "median_weeks": 4,
            "min_samples_median": 2,
            "short_days": 7,
            "min_samples_short": 3,
            "last_year_weeks": [4, 5],
        },
    }
    gap = config["gap_days"]
    clean = recent.recent_levels(columns, config)
    cut = START + 100 * DAY
    poisoned = copy.deepcopy(columns)
    poisoned["foot_traffic"][poisoned["slot_start"] >= cut] = 1e6
    changed = recent.recent_levels(poisoned, config)
    before = columns["slot_start"] < cut + gap * DAY
    for name in ("level_dow_hour_median", "level_trend", "level_last_year"):
        np.testing.assert_allclose(
            clean[name][before], changed[name][before], rtol=1e-6, equal_nan=True
        )
        assert np.isfinite(clean[name][columns["slot_start"] > START + 60 * DAY]).all()


def test_add_vacation_marks_configured_months() -> None:
    columns = make_columns()
    add_vacation(columns, [1, 2, 8])
    month = columns["slot_start"].astype("datetime64[M]").astype(int) % 12 + 1
    assert np.array_equal(columns["is_vacation"] == 1, np.isin(month, [1, 2, 8]))


def test_summarize_folds_reports_mean_std_and_worst_fold() -> None:
    def fold(start: str, model: float, base: float) -> dict:
        return {
            "eval_start": start,
            "metrics": {
                "model": {"mae": model, "rmse": model, "wape": 0.1},
                "baseline": {"mae": base, "rmse": base, "wape": 0.1},
                "improvement": {
                    "mae": (base - model) / base,
                    "rmse": 0.0,
                    "wape": 0.0,
                },
            },
            "by_sensor": {"1": {"model_mae": model, "baseline_mae": base}},
        }

    summary = walk_forward.summarize_folds(
        [fold("a", 10.0, 12.0), fold("b", 20.0, 18.0), fold("c", 14.0, 16.0)]
    )
    assert summary["model"]["mae"]["mean"] == pytest.approx(14.6667, abs=1e-3)
    assert summary["model"]["mae"]["std"] == pytest.approx(5.0332, abs=1e-3)
    assert summary["worst_fold_by_model_mae"] == "b"
    assert summary["folds_model_beats_baseline"] == 2
    assert summary["by_sensor"]["1"]["folds"] == 3
