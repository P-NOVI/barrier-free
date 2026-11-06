"""제보 사진 저장소. Supabase Storage 키가 있으면 거기에, 없으면 로컬 폴더에 둔다."""

from pathlib import Path
from typing import Protocol

import httpx

from app.config import Settings


class PhotoStorageError(Exception):
    """저장소에 닿지 못했거나 저장소가 거절했다."""


class PhotoStorage(Protocol):
    def save(self, name: str, content: bytes, media_type: str) -> None: ...

    def read(self, name: str) -> bytes | None:
        """없으면 None"""
        ...

    def delete(self, name: str) -> None:
        """없는 사진을 지워도 오류가 아니다."""
        ...


class LocalPhotoStorage:
    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def save(self, name: str, content: bytes, media_type: str) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        (self.directory / name).write_bytes(content)

    def read(self, name: str) -> bytes | None:
        path = self.directory / name
        return path.read_bytes() if path.is_file() else None

    def delete(self, name: str) -> None:
        (self.directory / name).unlink(missing_ok=True)


class SupabasePhotoStorage:
    """비공개 버킷. 서비스 키로 서버만 읽고 쓴다. 브라우저에는 주소를 주지 않는다."""

    def __init__(self, client: httpx.Client, bucket: str) -> None:
        self.client = client
        self.bucket = bucket

    def request(self, method: str, path: str, **kwargs: object) -> httpx.Response:
        try:
            return self.client.request(method, path, **kwargs)
        except httpx.HTTPError as error:
            # 오류 문구에 주소·키가 섞일 수 있어 종류만 남긴다.
            raise PhotoStorageError(type(error).__name__) from error

    def save(self, name: str, content: bytes, media_type: str) -> None:
        response = self.request(
            "POST",
            f"/object/{self.bucket}/{name}",
            content=content,
            headers={"Content-Type": media_type},
        )
        if not response.is_success:
            raise PhotoStorageError(f"save HTTP {response.status_code}")

    def read(self, name: str) -> bytes | None:
        response = self.request("GET", f"/object/authenticated/{self.bucket}/{name}")
        if response.status_code in (400, 404):
            # 없는 파일을 Supabase 는 400 또는 404 로 알린다.
            return None
        if not response.is_success:
            raise PhotoStorageError(f"read HTTP {response.status_code}")
        return response.content

    def delete(self, name: str) -> None:
        response = self.request("DELETE", f"/object/{self.bucket}/{name}")
        if not response.is_success and response.status_code not in (400, 404):
            raise PhotoStorageError(f"delete HTTP {response.status_code}")


def create_supabase_client(
    settings: Settings, transport: httpx.BaseTransport | None = None
) -> httpx.Client:
    key = settings.supabase_service_key.get_secret_value()
    return httpx.Client(
        base_url=f"{settings.supabase_url.rstrip('/')}/storage/v1",
        headers={"apikey": key, "Authorization": f"Bearer {key}"},
        timeout=settings.supabase_timeout_s,
        transport=transport,
    )


def supabase_configured(settings: Settings) -> bool:
    return bool(
        settings.supabase_url and settings.supabase_service_key.get_secret_value()
    )


def create_photo_storage(
    settings: Settings, transport: httpx.BaseTransport | None = None
) -> tuple[PhotoStorage, httpx.Client | None]:
    """저장소와, 다 쓴 뒤 닫아야 하는 HTTP client(로컬이면 None)."""
    if not supabase_configured(settings):
        return LocalPhotoStorage(settings.report_photo_dir), None
    client = create_supabase_client(settings, transport)
    return SupabasePhotoStorage(client, settings.supabase_photo_bucket), client
