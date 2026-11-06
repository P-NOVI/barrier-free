from fastapi import APIRouter, HTTPException, status

from app.deps import CongestionCacheDep, SdotClientDep, SensorsDep, SettingsDep
from app.schemas import CongestionResponse, RouteError, SensorCongestionResponse
from app.services.congestion_service import CongestionError, read_congestion

router = APIRouter(tags=["congestion"])


@router.get(
    "/congestion",
    response_model=CongestionResponse,
    responses={502: {"model": RouteError}, 503: {"model": RouteError}},
)
def get_congestion(
    client: SdotClientDep,
    sensors: SensorsDep,
    settings: SettingsDep,
    cache: CongestionCacheDep,
) -> CongestionResponse:
    try:
        readings = read_congestion(client, sensors, settings, cache)
    except CongestionError as error:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            detail={
                "reason": "congestion_failed",
                "message": "혼잡도를 가져오지 못했습니다. 잠시 뒤 다시 시도하세요.",
            },
        ) from error
    return CongestionResponse(
        sensors=[
            SensorCongestionResponse(
                code=reading.sensor.code,
                position=reading.sensor.position,
                address=reading.sensor.address,
                visitor_count=reading.visitor_count,
                measured_at=reading.measured_at,
            )
            for reading in readings
        ]
    )
