// 카카오맵 SDK 로드와 좌표 변환. 좌표 순서 변환은 이 파일에서만 한다.
// 백엔드·data/processed 는 GeoJSON 순서 [lng, lat], 카카오맵은 LatLng(lat, lng) 순서다.

const SDK_URL = 'https://dapi.kakao.com/v2/maps/sdk.js';

export type LngLat = [lng: number, lat: number];

// 지도 첫 화면 중심이자 검색 기준 좌표가 없을 때 쓰는 곳
export const SEOUL_CITY_HALL: LngLat = [126.9779, 37.5663];

let loading: Promise<typeof kakao.maps> | null = null;

export function sdkUrl(appKey: string): string {
    const params = new URLSearchParams({ appkey: appKey, autoload: 'false' });
    return `${SDK_URL}?${params}`;
}

/** SDK 스크립트를 한 번만 넣고, 로드가 끝나면 kakao.maps 를 돌려준다. */
export function loadKakaoMaps(
    appKey = import.meta.env.VITE_KAKAO_MAP_APP_KEY,
): Promise<typeof kakao.maps> {
    if (!appKey) {
        return Promise.reject(
            new Error(
                'VITE_KAKAO_MAP_APP_KEY 가 없습니다. frontend/.env 를 확인하세요.',
            ),
        );
    }
    loading ??= new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.src = sdkUrl(appKey);
        script.async = true;
        script.onload = () => kakao.maps.load(() => resolve(kakao.maps));
        script.onerror = () => {
            loading = null;
            script.remove();
            reject(
                new Error(
                    '카카오맵 SDK 를 불러오지 못했습니다. 키와 도메인 등록을 확인하세요.',
                ),
            );
        };
        document.head.append(script);
    });
    return loading;
}

export function toLatLng([lng, lat]: LngLat): kakao.maps.LatLng {
    return new kakao.maps.LatLng(lat, lng);
}

export function toLngLat(latLng: kakao.maps.LatLng): LngLat {
    return [latLng.getLng(), latLng.getLat()];
}

type Box = { left: number; top: number; right: number; bottom: number };

/**
 * box(지도 화면 기준 px)가 inset 안쪽에 들어오도록 지도를 얼마나 옮길지 (panBy 인자).
 * 위·왼쪽을 우선하고, 이미 들어와 있으면 0 이다.
 */
export function panToFit(
    box: Box,
    view: { width: number; height: number },
    inset: Box,
): [dx: number, dy: number] {
    const dx =
        box.left < inset.left
            ? box.left - inset.left
            : Math.max(0, box.right - (view.width - inset.right));
    const dy =
        box.top < inset.top
            ? box.top - inset.top
            : Math.max(0, box.bottom - (view.height - inset.bottom));
    return [dx, dy];
}
