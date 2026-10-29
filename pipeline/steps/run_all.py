"""pipeline 00~04 단계를 필요한 것만 순서대로 실행한다.

실행: pipeline/ 에서 uv run python steps/run_all.py [--force] [--from 02]
- 결과 파일이 이미 있는 단계는 건너뛴다.
- 어떤 단계를 다시 만들면 그 결과를 쓰는 뒤 단계도 다시 만든다.
- --force 는 모든 단계, --from NN 은 NN 단계와 그 뒤 단계를 다시 만든다.
"""

import argparse
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from common import CONFIG_PATH, data_dir, data_path, load_config, repo_path

STEPS_DIR = Path(__file__).resolve().parent

Config = dict[str, Any]


@dataclass(frozen=True)
class Step:
    number: str
    title: str
    script: str
    outputs: Callable[[Config], list[Path]]
    # 이 단계가 결과를 읽어 쓰는 앞 단계 번호
    needs: tuple[str, ...] = ()


STEPS = [
    Step(
        "00",
        "DEM 만들기",
        "00_build_dem.py",
        lambda c: [data_path(c["dem"]["output"])],
    ),
    Step(
        "01",
        "보행 도로망 받기",
        "01_fetch_network.py",
        lambda c: [data_path(c["network"]["output"])],
    ),
    Step(
        "02",
        "고도·경사 계산",
        "02_add_elevation.py",
        lambda c: [data_path(c["elevation"]["output"])],
        needs=("00", "01"),
    ),
    Step(
        "03",
        "계단·통행 가능 여부",
        "03_tag_barriers.py",
        lambda c: [data_path(c["barriers"]["output"])],
        needs=("02",),
    ),
    Step(
        "04",
        "graph.json.gz 내보내기",
        "04_export_graph.py",
        lambda c: [repo_path(c["export"]["output"])],
        needs=("03",),
    ),
]


def plan(
    steps: list[Step],
    config: Config,
    *,
    force: bool = False,
    start_from: str | None = None,
    exists: Callable[[Path], bool] = Path.exists,
) -> list[tuple[Step, bool]]:
    """단계마다 (단계, 실행 여부). 결과가 없거나 읽는 앞 단계가 다시 만들어지면 실행."""
    rebuilt: set[str] = set()
    result = []
    for step in steps:
        run = (
            force
            or step.number == start_from
            or any(need in rebuilt for need in step.needs)
            or not all(exists(path) for path in step.outputs(config))
        )
        if run:
            rebuilt.add(step.number)
        result.append((step, run))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    parser.add_argument("--force", action="store_true", help="모든 단계 다시 실행")
    parser.add_argument(
        "--from",
        dest="start_from",
        choices=[step.number for step in STEPS],
        help="이 단계와 그 뒤 단계를 다시 실행",
    )
    args = parser.parse_args()
    config = load_config(args.config)

    print(f"데이터 폴더: {data_dir()}", flush=True)
    steps = plan(STEPS, config, force=args.force, start_from=args.start_from)
    for step, run in steps:
        print(
            f"  {step.number} {step.title}: {'실행' if run else '건너뜀 (결과 있음)'}"
        )

    for step, run in steps:
        if not run:
            continue
        print(f"\n== {step.number} {step.title}", flush=True)
        started = time.time()
        command = [
            sys.executable,
            str(STEPS_DIR / step.script),
            "--config",
            str(args.config),
        ]
        if subprocess.run(command, check=False).returncode != 0:
            raise SystemExit(f"{step.number} {step.title} 단계에서 멈췄습니다.")
        print(f"== {step.number} 완료 ({time.time() - started:.0f}s)", flush=True)
    print("\n모든 단계 완료", flush=True)


if __name__ == "__main__":
    main()
