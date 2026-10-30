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
