from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.deps import KmaClientDep, SettingsDep, WeatherCacheDep
from app.schemas import RouteError, WeatherResponse
from app.services.weather_service import (
    KST,
    WeatherError,
    WeatherRangeError,
    read_weather,
)

router = APIRouter(tags=["weather"])


@router.get(
    "/weather",
    response_model=WeatherResponse,
    responses={
        422: {"model": RouteError},
        502: {"model": RouteError},
        503: {"model": RouteError},
    },
)
def get_weather(
    client: KmaClientDep,
    settings: SettingsDep,
    cache: WeatherCacheDep,
    lat: Annotated[float, Query(ge=-90, le=90, description="위도")],
    lon: Annotated[float, Query(ge=-180, le=180, description="경도")],
    at: Annotated[
        datetime | None,
        Query(
            description="날씨를 알고 싶은 시각(도착 시각). 가까운 정시로 맞춘다. "
            "시간대가 없으면 한국 시간. 없으면 지금"
        ),
    ] = None,
) -> WeatherResponse:
    when = at or datetime.now(KST)
    if when.tzinfo is None:
        when = when.replace(tzinfo=KST)
    try:
        weather = read_weather(client, lat, lon, when, settings, cache)
    except WeatherRangeError as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"reason": "weather_out_of_range", "message": str(error)},
        ) from error
    except WeatherError as error:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            detail={
                "reason": "weather_failed",
                "message": "날씨를 가져오지 못했습니다. 잠시 뒤 다시 시도하세요.",
            },
        ) from error
    return WeatherResponse(
        source=weather.source,
        time=weather.time,
        temp_c=weather.temp_c,
        rain_mm=weather.rain_mm,
        precipitation=weather.precipitation,
    )
