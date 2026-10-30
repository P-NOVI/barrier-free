// GET /api/places/search 호출. 응답 형식은 backend/app/schemas.py 의 PlaceSearchResponse 와 같다.

import { type ApiOptions, requestJson } from './apiClient';
import type { LngLat } from './kakaoMap';

export type Place = {
    name: string;
    /** 지번 주소 */
    address: string;
    /** 도로명 주소. 없으면 빈 문자열 */
    road_address: string;
    category: string;
    position: LngLat;
    /** near 에서 거리. near 없이 검색하면 null */
    distance_m: number | null;
};

/** near 를 주면 그 근처 장소를 앞에 두고 거리를 함께 돌려준다. */
export async function searchPlaces(
    query: string,
    near: LngLat | null,
    options?: ApiOptions,
): Promise<Place[]> {
    const params: Record<string, string> = { query };
    if (near) {
        params.lng = String(near[0]);
        params.lat = String(near[1]);
    }
    const { places } = await requestJson<{ places: Place[] }>(
        {
            path: '/api/places/search',
            query: params,
            failureMessage: '장소를 찾지 못했습니다.',
        },
        options,
    );
    return places;
}

/** GET /api/places/address 응답. backend/app/schemas.py 의 AddressResponse 와 같다. */
export type Address = {
    /** 화면에 보일 이름: 건물 이름 → 근처 랜드마크 → 동 + 지번 (백엔드가 정한다) */
    name: string;
    /** 건물 이름. 없으면 빈 문자열 */
    building_name: string;
    /** 도로명 주소. 없으면 빈 문자열 */
    road_address: string;
    /** 지번 주소 */
    address: string;
};

/** 좌표의 주소. 주소가 없는 곳이면 null */
export async function findAddress(
    position: LngLat,
    options?: ApiOptions,
): Promise<Address | null> {
    const { address } = await requestJson<{ address: Address | null }>(
        {
            path: '/api/places/address',
            query: { lng: String(position[0]), lat: String(position[1]) },
            failureMessage: '주소를 찾지 못했습니다.',
        },
        options,
    );
    return address;
}
