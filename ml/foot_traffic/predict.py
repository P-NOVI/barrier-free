"""하루 예측을 직접 확인한다: 센서와 날짜를 넣으면 시간대별 예측을 표와 그래프로 본다.

실행: ml/ 에서 uv run python -m foot_traffic.predict --sensor 3020 --date 2026-10-10
- 입력: 학습한 모델(models/foot_traffic_model.txt)과 학습셋의 그날 실측·날씨·달력.
- --rain(mm), --temp(℃)를 주면 그날 모든 시간의 강수·기온을 바꿔 다시 예측한
  선을 더한다.
- 출력: 터미널 표와 models/predict_<센서>_<날짜>.png (--out 으로 바꾼다).
- baseline 은 그 센서의 테스트 시작 전(학습+검증) 센서·요일·시각별 중앙값이다.
  테스트 시작 전 날짜는 모델이 학습에 쓴 날이라 실제 성능보다 잘 맞는다.
  학습에 쓰지 않은 날은 split.test_start 이후다.
"""

import argparse
import json
from pathlib import Path
from typing import Any

import lightgbm as lgb
import numpy as np

from foot_traffic import baseline, metrics
from foot_traffic.common import CONFIG_PATH, data_path, load_config, repo_path
from foot_traffic.data import (
    Columns,
    add_off_adjacent,
    build_features,
    load_columns,
    take,
)
from foot_traffic.train import FULL_GROUPS

WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]
FONTS = ["Malgun Gothic", "AppleGothic", "NanumGothic", "DejaVu Sans"]
DPI = 130


def select_day(columns: Columns, sensor: int, day: str) -> np.ndarray:
    """센서와 날짜(YYYY-MM-DD)에 맞는 행 마스크."""
    days = columns["slot_start"].astype("datetime64[D]")
    return (columns["sensor_code"] == sensor) & (days == np.datetime64(day))


def day_tags(part: Columns) -> str:
    """그날의 달력 설명(공휴일, 쉬는 날 전날 등). 해당 없으면 빈 문자열."""
    tags = []
    if part["is_holiday"][0] == 1:
        tags.append("공휴일")
    elif part["is_off_day"][0] == 1:
        tags.append("주말")
    if part["is_before_off_day"][0] == 1:
        tags.append("쉬는 날 전날")
    if part["is_after_off_day"][0] == 1:
        tags.append("쉬는 날 다음날")
    return ", ".join(tags)


def model_predict(
    booster: lgb.Booster,
    part: Columns,
    vocab: dict[str, list[Any]],
    config: dict[str, Any],
    expected_names: list[str],
) -> np.ndarray:
    matrix, names = build_features(part, vocab, config["features"], FULL_GROUPS)
    if names != expected_names:
        raise SystemExit("모델의 피처 목록과 config.yaml 이 다릅니다. 다시 학습하세요.")
    return np.clip(booster.predict(matrix), 0.0, None)


def baseline_predict(
    columns: Columns, part: Columns, sensor: int, test_start: str
) -> np.ndarray:
    """그 센서의 테스트 시작 전 행으로 만든 센서·요일·시각별 중앙값."""
    mask = (columns["sensor_code"] == sensor) & (
        columns["slot_start"] < np.datetime64(test_start)
    )
    source = take(columns, mask)
    keys = baseline.slot_keys(
        source["sensor_code"], source["day_of_week"], source["hour_of_day"]
    )
    by_slot, by_sensor = baseline.fit_baseline(
        keys, source["sensor_code"], source["foot_traffic"], "median"
    )
    target_keys = baseline.slot_keys(
        part["sensor_code"], part["day_of_week"], part["hour_of_day"]
    )
    return baseline.predict_baseline(
        target_keys, part["sensor_code"], by_slot, by_sensor
    )


def format_table(
    part: Columns, model: np.ndarray, base: np.ndarray, what_if: np.ndarray | None
) -> str:
    header = f"{'시각':>4} {'실제':>7} {'모델':>7} {'baseline':>8}"
    if what_if is not None:
        header += f" {'가정':>7}"
    header += f" {'기온':>6} {'강수':>6}"
    lines = [header]
    for i, hour in enumerate(part["hour_of_day"]):
        line = (
            f"{int(hour):>3}시 {part['foot_traffic'][i]:>7.0f} {model[i]:>7.0f} "
            f"{base[i]:>8.0f}"
        )
        if what_if is not None:
            line += f" {what_if[i]:>7.0f}"
        line += f" {part['temp'][i]:>6.1f} {part['rain_mm'][i]:>6.1f}"
        lines.append(line)
    return "\n".join(lines)


def plot_day(
    path: Path,
    title: str,
    part: Columns,
    model: np.ndarray,
    base: np.ndarray,
    what_if: np.ndarray | None,
    what_if_label: str,
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager

    installed = {font.name for font in font_manager.fontManager.ttflist}
    plt.rcParams["font.family"] = next(
        (name for name in FONTS if name in installed), "DejaVu Sans"
    )
    plt.rcParams["axes.unicode_minus"] = False
    hours = part["hour_of_day"]
    fig, (top, bottom) = plt.subplots(
        2, 1, figsize=(9, 6), sharex=True, gridspec_kw={"height_ratios": [3, 1]}
    )
    top.plot(hours, part["foot_traffic"], color="black", marker="o", label="실제")
    top.plot(hours, model, color="tab:blue", marker="o", label="모델 예측")
    top.plot(hours, base, color="tab:gray", linestyle="--", label="baseline 중앙값")
    if what_if is not None:
        top.plot(hours, what_if, color="tab:red", marker="s", label=what_if_label)
    top.set_ylim(bottom=0)
    top.set_ylabel("유동인구 (명/시간)")
    top.set_title(title)
    top.grid(alpha=0.3)
    top.legend()
    bottom.bar(hours, part["rain_mm"], color="tab:cyan")
    bottom.set_ylim(0, max(1.0, float(np.nanmax(part["rain_mm"])) * 1.1))
    bottom.set_xlim(-0.5, 23.5)
    bottom.set_ylabel("강수 (mm)")
    bottom.set_xlabel("시각 (한 시간 구간의 시작)")
    bottom.set_xticks(range(0, 24, 2))
    bottom.grid(alpha=0.3)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=DPI)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    parser.add_argument("--sensor", type=int, required=True, help="센서 코드")
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--rain", type=float, help="그날 모든 시간의 강수(mm)로 가정")
    parser.add_argument("--temp", type=float, help="그날 모든 시간의 기온(℃)으로 가정")
    parser.add_argument("--out", type=Path, help="그래프 PNG 경로")
    args = parser.parse_args()
    config = load_config(args.config)
    data = config["data"]

    columns = load_columns(data_path(data["training_set"]))
    add_off_adjacent(columns, data_path(data["calendar"]))
    mask = select_day(columns, args.sensor, args.date)
    if not mask.any():
        sensor_slots = columns["slot_start"][columns["sensor_code"] == args.sensor]
        if sensor_slots.size == 0:
            raise SystemExit(f"학습셋에 센서 {args.sensor} 가 없습니다.")
        raise SystemExit(
            f"센서 {args.sensor} 의 {args.date} 행이 없습니다. 있는 기간: "
            f"{sensor_slots.min().astype('datetime64[D]')} ~ "
            f"{sensor_slots.max().astype('datetime64[D]')} (빠진 날도 있을 수 있습니다)"
        )
    part = take(columns, mask)
    order = np.argsort(part["hour_of_day"])
    part = take(part, order)

    meta_path = repo_path(f"{data['model_dir']}/{data['meta_file']}")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    booster = lgb.Booster(
        model_file=str(repo_path(f"{data['model_dir']}/{data['model_file']}"))
    )
    vocab = meta["vocab"]
    names = meta["feature_names"]
    model = model_predict(booster, part, vocab, config, names)
    base = baseline_predict(columns, part, args.sensor, config["split"]["test_start"])

    what_if, what_if_label = None, ""
    if args.rain is not None or args.temp is not None:
        changed = {key: values.copy() for key, values in part.items()}
        parts = []
        if args.rain is not None:
            changed["rain_mm"][:] = args.rain
            parts.append(f"강수 {args.rain:g}mm")
        if args.temp is not None:
            changed["temp"][:] = args.temp
            parts.append(f"기온 {args.temp:g}℃")
        what_if = model_predict(booster, changed, vocab, config, names)
        what_if_label = "가정: " + ", ".join(parts)

    weekday = WEEKDAYS[int(part["day_of_week"][0])]
    tags = day_tags(part)
    title = f"센서 {args.sensor} · {args.date} ({weekday})" + (
        f" · {tags}" if tags else ""
    )
    print(title)
    print(format_table(part, model, base, what_if))
    actual = part["foot_traffic"]
    print(
        f"MAE 모델 {metrics.mae(actual, model):.1f}명 / "
        f"baseline {metrics.mae(actual, base):.1f}명 "
        f"(오차율 모델 {metrics.error_rate(actual, model):.1%} / "
        f"baseline {metrics.error_rate(actual, base):.1%})"
    )
    if args.date < config["split"]["test_start"]:
        print(
            "주의: 이 날짜는 모델 학습에 쓴 구간이라 실제 성능보다 잘 맞을 수 있습니다."
        )

    out = args.out or repo_path(
        f"{data['model_dir']}/predict_{args.sensor}_{args.date}.png"
    )
    plot_day(out, title, part, model, base, what_if, what_if_label)
    print(f"그래프 {out}")


if __name__ == "__main__":
    main()
