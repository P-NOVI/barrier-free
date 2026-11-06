"""Vercel 빌드 때 루트 data/processed 의 서버 데이터를 backend/vercel_data 로 복사한다.

Vercel 백엔드 프로젝트의 Root Directory 는 backend 라서, 루트의 data/ 는 함수에 들어가지
않는다. 복사한 파일 경로는 환경변수(GRAPH_PATH 등)로 넘긴다(DEPLOY.md).
"""

import shutil
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
SOURCE_DIR = BACKEND_DIR.parent / "data" / "processed"
TARGET_DIR = BACKEND_DIR / "vercel_data"
# app/config.py 의 *_path 설정이 가리키는 파일
FILES = ("graph.json.gz", "entrances.json.gz", "sites.json.gz", "sdot_sensors.json")


def copy_data(source: Path, target: Path) -> list[Path]:
    """FILES 를 source 에서 target 으로 복사한다. 하나라도 없으면 빌드를 멈춘다."""
    missing = [name for name in FILES if not (source / name).is_file()]
    if missing:
        raise SystemExit(f"{source} 에 없는 파일: {', '.join(missing)}")
    target.mkdir(parents=True, exist_ok=True)
    return [Path(shutil.copy2(source / name, target / name)) for name in FILES]


if __name__ == "__main__":
    for path in copy_data(SOURCE_DIR, TARGET_DIR):
        print(f"{path.name} {path.stat().st_size / 1e6:.1f} MB")
    sys.exit(0)
