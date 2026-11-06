from pathlib import Path

import pytest

from foot_traffic import storage

FILES = ["interim/a/x.parquet", "models/m/model.txt"]


class FakeClient:
    """boto3 S3 client 대신 쓴다. 올린 파일 내용을 들고 있다."""

    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}

    def upload_file(self, path: str, bucket: str, key: str) -> None:
        self.objects[(bucket, key)] = Path(path).read_bytes()

    def download_file(self, bucket: str, key: str, path: str) -> None:
        Path(path).write_bytes(self.objects[(bucket, key)])


def make_files(root: Path, sizes: list[int]) -> None:
    for key, size in zip(FILES, sizes):
        path = root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x" * size)


def test_upload_then_download_keeps_relative_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shared = tmp_path / "shared"
    make_files(shared, [10, 20])
    monkeypatch.setenv("DATA_DIR", str(shared))
    client = FakeClient()

    storage.upload(client, "bucket", FILES, max_mb=50)
    dest = tmp_path / "runner"
    storage.download(client, "bucket", FILES, dest)

    assert set(client.objects) == {("bucket", key) for key in FILES}
    assert (dest / FILES[1]).read_bytes() == b"x" * 20


def test_upload_refuses_large_or_missing_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_files(tmp_path, [10, 3_000_000])
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    client = FakeClient()

    with pytest.raises(SystemExit, match="MB 를 넘어"):
        storage.upload(client, "bucket", FILES, max_mb=2)
    with pytest.raises(SystemExit, match="없는 파일"):
        storage.upload(client, "bucket", [*FILES, "interim/none.parquet"], max_mb=50)
    assert client.objects == {}


def test_client_settings_need_all_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for env in storage.ENV_NAMES.values():
        monkeypatch.setenv(env, "v")
    assert set(storage.client_settings()) == set(storage.ENV_NAMES)

    monkeypatch.setenv("STORAGE_S3_REGION", "")
    with pytest.raises(SystemExit, match="STORAGE_S3_REGION"):
        storage.client_settings()
