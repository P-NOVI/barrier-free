"""pipeline 단계 공통: 설정 읽기와 데이터 경로.

데이터 경로는 pipeline/.env 의 DATA_DIR(Google Drive 공유 폴더 등) 기준이고,
없으면 저장소의 data/ 를 쓴다. 서버가 읽는 결과(data/processed)는 저장소 기준이다.
"""

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

PIPELINE_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = PIPELINE_DIR.parent
CONFIG_PATH = PIPELINE_DIR / "config.yaml"
ENV_PATH = PIPELINE_DIR / ".env"

load_dotenv(ENV_PATH)


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def data_dir() -> Path:
    """공유 데이터 폴더. DATA_DIR 이 비어 있으면 저장소의 data/."""
    value = os.environ.get("DATA_DIR", "").strip().strip('"')
    return Path(value).expanduser() if value else REPO_ROOT / "data"


def data_path(relative: str) -> Path:
    """config.yaml 의 데이터 경로(raw/…, interim/…) → 실제 경로."""
    return data_dir() / relative


def repo_path(relative: str) -> Path:
    """config.yaml 의 저장소 경로(data/processed/…) → 실제 경로."""
    return REPO_ROOT / relative


def require_files(*paths: Path) -> None:
    """입력 파일이 없으면 원인과 할 일을 알려 주고 멈춘다."""
    missing = [path for path in paths if not path.exists()]
    if not missing:
        return
    lines = "\n".join(f"  - {path}" for path in missing)
    raise SystemExit(
        f"필요한 파일이 없습니다.\n{lines}\n"
        f"데이터 폴더: {data_dir()}\n"
        "- 공유 폴더를 쓰면 Google Drive 데스크톱이 켜져 있는지, "
        "pipeline/.env 의 DATA_DIR 이 맞는지 확인하세요.\n"
        "- 앞 단계 결과가 없으면 steps/run_all.py 로 앞 단계부터 실행하세요."
    )
