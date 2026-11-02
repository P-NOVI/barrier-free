import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from app.config import Settings
from app.repositories.sensor_repository import Sensor

SERVICE_NAME = "sDoTPeople"
OK_CODE = "INFO-000"
# 조건에 맞는 데이터가 없을 때 오는 코드. 오류가 아니라 빈 결과로 다룬다.
NO_DATA_CODE = "INFO-200"
SENSING_TIME_FORMAT = "%Y-%m-%d_%H:%M:%S"
KST = timezone(timedelta(hours=9))


@dataclass(frozen=True)
class Reading:
    sensor: Sensor
    visitor_count: int
    measured_at: datetime


class CongestionError(Exception):
    """S-DoT API 호출이나 응답 해석이 실패했을 때."""


class TtlCache[T]:
    """값 하나를 ttl_s 초 동안 들고 있는다."""

    def __init__(
        self, ttl_s: float, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self.ttl_s = ttl_s
        self.clock = clock
        self.entry: tuple[float, T] | None = None

    def get(self) -> T | None:
        if self.entry is None or self.clock() - self.entry[0] >= self.ttl_s:
            return None
        return self.entry[1]

    def set(self, value: T) -> None:
        self.entry = (self.clock(), value)


def create_sdot_client(
    settings: Settings, transport: httpx.BaseTransport | None = None
) -> httpx.Client:
    api_key = settings.sdot_api_key.get_secret_value()
    return httpx.Client(
        base_url=f"{settings.sdot_base_url}/{api_key}/json",
        timeout=settings.sdot_timeout_s,
        transport=transport,
    )


def read_congestion(
    client: httpx.Client,
    sensors: Mapping[int, Sensor],
    settings: Settings,
    cache: TtlCache[list[Reading]],
) -> list[Reading]:
    """센서별 가장 최근 유동인구. 캐시가 살아 있으면 API를 부르지 않는다."""
    cached = cache.get()
    if cached is not None:
        return cached
    rows = request_rows(client, settings.sdot_page_size)
    readings = latest_readings(rows, sensors)
    cache.set(readings)
    return readings


def request_rows(client: httpx.Client, page_size: int) -> list[dict[str, Any]]:
    try:
        response = client.get(f"/{SERVICE_NAME}/1/{page_size}/")
        response.raise_for_status()
        body = response.json()
        # 성공하면 서비스 이름 아래에, 인증 오류 같은 실패는 바로 RESULT 로 온다.
        payload = body.get(SERVICE_NAME, body)
        code = payload["RESULT"]["CODE"]
        if code == NO_DATA_CODE:
            return []
        if code != OK_CODE:
            raise CongestionError(code)
        return payload["row"]
    except CongestionError:
        raise
    except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError):
        # 요청 주소에 API 키가 들어 있어서 원인 예외(주소 포함)를 잇지 않는다.
        raise CongestionError from None


def latest_readings(
    rows: list[dict[str, Any]], sensors: Mapping[int, Sensor]
) -> list[Reading]:
    """위치를 아는 센서만, 센서마다 측정 시각이 가장 늦은 행을 남긴다."""
    latest: dict[int, Reading] = {}
    for row in rows:
        try:
            code = int(row["SERIAL"])
            reading = Reading(
                sensor=sensors[code],
                visitor_count=int(row["VISITOR_COUNT"]),
                measured_at=datetime.strptime(
                    row["SENSING_TIME"], SENSING_TIME_FORMAT
                ).replace(tzinfo=KST),
            )
        except (KeyError, ValueError, TypeError):
            # 위치 파일에 없는 센서와 값이 깨진 행은 건너뛴다.
            continue
        known = latest.get(code)
        if known is None or reading.measured_at > known.measured_at:
            latest[code] = reading
    return sorted(latest.values(), key=lambda reading: reading.sensor.code)
