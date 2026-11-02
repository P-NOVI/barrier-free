// 브라우저 현재 위치. 좌표는 저장하지 않고 요청한 곳에만 돌려준다.

import type { LngLat } from './kakaoMap';

// 정확한 위치(GPS)를 먼저 기다리고, 실패하면 Wi-Fi·기지국 기반 위치로 다시 묻는다.
const PRECISE: PositionOptions = { enableHighAccuracy: true, timeout: 10_000 };
const COARSE: PositionOptions = {
    enableHighAccuracy: false,
    timeout: 10_000,
    maximumAge: 60_000,
};
// 안내 중에는 GPS 위치를 계속 받는다. 다음 위치가 늦어도 오류로 끊지 않는다.
const WATCH: PositionOptions = { enableHighAccuracy: true, maximumAge: 0 };

/** 찾은 위치 */
export type LocationFix = {
    position: LngLat;
    /** 오차 반경(m). 실제 위치는 이 원 안에 있을 가능성이 높다. */
    accuracy: number;
};

// GeolocationPositionError 코드
const PERMISSION_DENIED = 1;

export class LocationError extends Error {
    constructor(message: string) {
        super(message);
        this.name = 'LocationError';
    }
}

const UNSUPPORTED = '이 브라우저는 위치 찾기를 지원하지 않습니다.';

function toFix({ coords }: GeolocationPosition): LocationFix {
    return {
        position: [coords.longitude, coords.latitude],
        accuracy: coords.accuracy,
    };
}

function locate(
    geolocation: Geolocation,
    options: PositionOptions,
): Promise<LocationFix> {
    return new Promise((resolve, reject) =>
        geolocation.getCurrentPosition(
            (position) => resolve(toFix(position)),
            reject,
            options,
        ),
    );
}

function isPermissionDenied(error: unknown): boolean {
    return (
        error instanceof Object &&
        'code' in error &&
        error.code === PERMISSION_DENIED
    );
}

function toLocationError(error: unknown): LocationError {
    return new LocationError(
        isPermissionDenied(error)
            ? '위치 권한이 꺼져 있습니다. 브라우저 설정에서 위치 권한을 허용하세요.'
            : '현재 위치를 찾지 못했습니다. 잠시 뒤 다시 시도하거나 장소를 검색하세요.',
    );
}

export async function getCurrentPosition(
    geolocation: Geolocation | undefined = globalThis.navigator?.geolocation,
): Promise<LocationFix> {
    if (!geolocation) {
        throw new LocationError(UNSUPPORTED);
    }
    try {
        return await locate(geolocation, PRECISE);
    } catch (error) {
        // 권한이 없으면 다시 물어도 같은 결과라 바로 알린다.
        if (isPermissionDenied(error)) {
            throw toLocationError(error);
        }
    }
    try {
        return await locate(geolocation, COARSE);
    } catch (error) {
        throw toLocationError(error);
    }
}

/**
 * 위치가 바뀔 때마다 onFix 로 알린다. 돌려준 함수를 부르면 멈춘다.
 * 위치를 잠시 못 받아도 멈추지 않고, 다음 위치가 오면 다시 onFix 를 부른다.
 */
export function watchLocation(
    onFix: (fix: LocationFix) => void,
    onError: (error: LocationError) => void,
    geolocation: Geolocation | undefined = globalThis.navigator?.geolocation,
): () => void {
    if (!geolocation) {
        onError(new LocationError(UNSUPPORTED));
        return () => undefined;
    }
    const id = geolocation.watchPosition(
        (position) => onFix(toFix(position)),
        (error) => onError(toLocationError(error)),
        WATCH,
    );
    return () => geolocation.clearWatch(id);
}
