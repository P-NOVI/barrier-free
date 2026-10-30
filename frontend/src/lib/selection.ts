import type { LngLat } from './kakaoMap';

export type Endpoint = {
    position: LngLat;
    /** 검색창에 보일 이름 (장소 이름, 현재 위치 등) */
    label: string;
};

export type Endpoints = {
    start: Endpoint | null;
    goal: Endpoint | null;
};

export type EndpointRole = keyof Endpoints;

export const NO_ENDPOINTS: Endpoints = { start: null, goal: null };

export const MAP_CLICK_LABEL = '지도에서 고른 위치';

/** 지도를 눌러 고른 장소. 이름·주소를 찾은 뒤에 만든다. */
export type PickedPlace = {
    position: LngLat;
    name: string | null;
    address: string | null;
};

/** found 가 null 이면 이름·주소를 못 찾은 것이다. */
export function toPickedPlace(
    position: LngLat,
    found: { name: string; address: string } | null,
): PickedPlace {
    return {
        position,
        name: found?.name ?? null,
        address: found?.address || null,
    };
}
