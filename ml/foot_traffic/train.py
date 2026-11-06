"""서비스용 유동인구 모델을 학습해 공유 폴더에 저장한다.

실행: ml/ 에서 uv run python -m foot_traffic.train [--rounds N]
- 입력: pipeline 13 단계 전체 학습셋(walk_forward.training_set)과 달력.
- 전처리·피처·하이퍼파라미터는 walk-forward 검증(walk_forward.py)과 같다. 가진 데이터
  전체로 학습하고, 반복 수는 walk-forward 기본 fold 반복 수의 중앙값(output_dir 의
  folds.json)이다. 먼저 walk_forward 를 실행해 두어야 한다.
- 출력: DATA_DIR 의 serve.model_dir(모델 txt, 메타 json). 팀원은 다시 학습하지 않고
  forecast.py 로 이 모델을 불러 예측한다.
- 성능은 walk-forward 최종 테스트(output_dir 의 final_test.json)로 보고한다. 이 모델은
  테스트 구간까지 학습하므로 따로 평가하지 않는다.
"""

import argparse
import json
import time
from pathlib import Path

from foot_traffic.common import CONFIG_PATH, data_path, load_config, repo_path
from foot_traffic.data import load_columns
from foot_traffic.walk_forward import (
    fit_service,
    median_rounds,
    save_booster,
    write_json,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    parser.add_argument(
        "--rounds",
        type=int,
        help="반복 수(기본: walk-forward 기본 fold 반복 수의 중앙값)",
    )
    args = parser.parse_args()
    config = load_config(args.config)
    wf, serve = config["walk_forward"], config["serve"]
    started = time.time()
    out = repo_path(wf["output_dir"])
    rounds = args.rounds or median_rounds(out)

    columns = load_columns(data_path(wf["training_set"]))
    print(f"전체 행 {columns['foot_traffic'].size:,}, 반복 {rounds}회", flush=True)
    booster, meta = fit_service(
        columns, config, data_path(config["data"]["calendar"]), rounds
    )
    final_path = out / "final_test.json"
    if final_path.exists():
        final = json.loads(final_path.read_text(encoding="utf-8"))
        meta["walk_forward_final_test"] = {
            "eval_start": final["eval_start"],
            "eval_end_exclusive": final["eval_end_exclusive"],
            "metrics": final["metrics"],
        }

    model_dir = data_path(serve["model_dir"])
    save_booster(booster, model_dir / serve["model_file"])
    write_json(model_dir / serve["meta_file"], meta)
    print(
        f"학습 {meta['train_rows']:,}행 ({meta['train_first_slot']} ~ "
        f"{meta['train_last_slot']}) → 공유 폴더 {serve['model_dir']} "
        f"({time.time() - started:.0f}s)",
        flush=True,
    )


if __name__ == "__main__":
    main()
