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
export const CURRENT_LOCATION_LABEL = '현재 위치';

/** 지도를 눌러 고르거나 검색해서 고른 장소. 이름·주소를 찾은 뒤에 만든다. */
export type PickedPlace = {
    position: LngLat;
    name: string | null;
    address: string | null;
    /** 장소 분류 (예: 카페). 검색으로 고른 장소만 있다. */
    category?: string | null;
};

/**
 * 카카오 분류(예: '음식점 > 카페 > 커피전문점 > 커피빈')에서 화면에 보일 이름.
 * 마지막 단계가 상호(장소 이름이 그 말로 시작)면 한 단계 위를 쓴다.
 */
export function categoryLabel(category: string, name: string): string | null {
    const parts = category
        .split('>')
        .map((part) => part.trim())
        .filter((part) => part !== '');
    const last = parts.at(-1);
    if (last === undefined) {
        return null;
    }
    if (parts.length > 1 && name.startsWith(last)) {
        return parts.at(-2) ?? null;
    }
    return last;
}

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
