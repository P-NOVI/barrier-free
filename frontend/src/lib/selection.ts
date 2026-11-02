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

/** 지도 클릭 순서: 출발 → 도착. 둘 다 고른 뒤 누르면 새 출발지로 다시 시작한다. */
export function selectEndpoint(current: Endpoints, clicked: LngLat): Endpoints {
    const endpoint = { position: clicked, label: MAP_CLICK_LABEL };
    if (current.start && !current.goal) {
        return { start: current.start, goal: endpoint };
    }
    return { start: endpoint, goal: null };
}
