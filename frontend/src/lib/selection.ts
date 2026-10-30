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

/** 지도 클릭 순서: 출발 → 도착. 둘 다 고른 뒤 누르면 새 출발지로 다시 시작한다. */
export function selectEndpoint(current: Endpoints, clicked: LngLat): Endpoints {
    const endpoint = { position: clicked, label: MAP_CLICK_LABEL };
    if (current.start && !current.goal) {
        return { start: current.start, goal: endpoint };
    }
    return { start: endpoint, goal: null };
}

/** 지도에서 고른 position 의 이름이 나중에 정해지면 그 출발·도착만 이름을 바꾼다. */
export function renameEndpoint(
    current: Endpoints,
    position: LngLat,
    label: string,
): Endpoints {
    // 이름을 찾는 사이 다른 곳을 골랐으면 그대로 둔다. 같은 클릭인지는 배열 자체로 구분한다.
    const rename = (endpoint: Endpoint | null) =>
        endpoint?.position === position ? { position, label } : endpoint;
    const next = { start: rename(current.start), goal: rename(current.goal) };
    return next.start === current.start && next.goal === current.goal
        ? current
        : next;
}
