"""매일 배치가 읽는 파일을 Supabase Storage(S3 호환)에 올리고 받는다.

실행: ml/ 에서
  uv run python -m foot_traffic.storage upload             # DATA_DIR → 버킷
  uv run python -m foot_traffic.storage download --dest 폴더  # 버킷 → 폴더
- 파일은 config.yaml 의 storage.files 이고, 버킷 안 경로는 DATA_DIR 기준 상대경로와
  같다. 그래서 받은 폴더를 DATA_DIR 로 두면 pipeline·ml 이 그대로 읽는다.
- 접속 정보는 ml/.env(또는 Actions Secrets)의 STORAGE_S3_ENDPOINT, STORAGE_S3_REGION,
  STORAGE_S3_ACCESS_KEY_ID, STORAGE_S3_SECRET_ACCESS_KEY 다. 값은 출력하지 않는다.
- 이력·날씨·달력을 다시 만들었거나 모델을 다시 학습했을 때 upload 한다.
"""

import argparse
import os
import sys
from pathlib import Path
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from foot_traffic.common import CONFIG_PATH, data_path, load_config

ENV_NAMES = {
    "endpoint_url": "STORAGE_S3_ENDPOINT",
    "region_name": "STORAGE_S3_REGION",
    "aws_access_key_id": "STORAGE_S3_ACCESS_KEY_ID",
    "aws_secret_access_key": "STORAGE_S3_SECRET_ACCESS_KEY",
}
MB = 1_000_000


def client_settings() -> dict[str, str]:
    """boto3 client 인자. 빠진 환경변수가 있으면 SystemExit."""
    values = {key: os.environ.get(env, "").strip() for key, env in ENV_NAMES.items()}
    missing = [ENV_NAMES[key] for key, value in values.items() if not value]
    if missing:
        raise SystemExit(f"환경변수가 비어 있습니다: {', '.join(missing)}")
    return values


def too_large(paths: list[tuple[str, Path]], max_mb: float) -> list[str]:
    """올릴 수 없을 만큼 큰 파일(상대경로, 크기)."""
    return [
        f"{key} ({path.stat().st_size / MB:.1f} MB)"
        for key, path in paths
        if path.stat().st_size > max_mb * MB
    ]


def upload(client: Any, bucket: str, files: list[str], max_mb: float) -> None:
    paths = [(key, data_path(key)) for key in files]
    missing = [key for key, path in paths if not path.exists()]
    if missing:
        raise SystemExit(f"공유 폴더에 없는 파일: {', '.join(missing)}")
    large = too_large(paths, max_mb)
    if large:
        raise SystemExit(
            f"파일당 {max_mb:.0f}MB 를 넘어 올릴 수 없습니다: {', '.join(large)}"
        )
    for key, path in paths:
        client.upload_file(str(path), bucket, key)
        print(f"올림 {key} ({path.stat().st_size / MB:.1f} MB)", flush=True)


def download(client: Any, bucket: str, files: list[str], dest: Path) -> None:
    for key in files:
        target = dest / key
        target.parent.mkdir(parents=True, exist_ok=True)
        client.download_file(bucket, key, str(target))
        print(f"받음 {key} ({target.stat().st_size / MB:.1f} MB)", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["upload", "download"])
    parser.add_argument("--dest", type=Path, help="download 할 폴더")
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    args = parser.parse_args()
    storage = load_config(args.config)["storage"]
    if args.action == "download" and args.dest is None:
        parser.error("download 에는 --dest 가 필요합니다.")
    client = boto3.client("s3", **client_settings())
    try:
        if args.action == "upload":
            upload(client, storage["bucket"], storage["files"], storage["max_file_mb"])
        else:
            download(client, storage["bucket"], storage["files"], args.dest)
    except (BotoCoreError, ClientError) as error:
        # 예외 문구에 주소가 섞일 수 있어 종류만 남긴다.
        print(f"Storage 요청 실패 ({type(error).__name__})")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
