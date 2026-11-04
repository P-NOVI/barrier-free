"""ml 공통: 설정 읽기와 데이터 경로.

데이터 경로는 pipeline 과 같은 규칙이다. ml/.env 의 DATA_DIR(Google Drive 공유 폴더
등) 기준이고, 없으면 저장소의 data/ 를 쓴다. 모델은 저장소 기준 경로에 둔다.
"""

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

ML_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = ML_DIR.parent
CONFIG_PATH = ML_DIR / "config.yaml"
ENV_PATH = ML_DIR / ".env"

load_dotenv(ENV_PATH)


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def data_dir() -> Path:
    """공유 데이터 폴더. DATA_DIR 이 비어 있으면 저장소의 data/."""
    value = os.environ.get("DATA_DIR", "").strip().strip('"')
    return Path(value).expanduser() if value else REPO_ROOT / "data"


def data_path(relative: str) -> Path:
    """config.yaml 의 데이터 경로(interim/…) → 실제 경로."""
    return data_dir() / relative


def repo_path(relative: str) -> Path:
    """config.yaml 의 저장소 경로(models/…) → 실제 경로."""
    return REPO_ROOT / relative
