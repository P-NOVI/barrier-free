import type { LngLat } from './kakaoMap';

export type Endpoints = {
    start: LngLat | null;
    goal: LngLat | null;
};

export const NO_ENDPOINTS: Endpoints = { start: null, goal: null };

/** 지도 클릭 순서: 출발 → 도착. 둘 다 고른 뒤 누르면 새 출발지로 다시 시작한다. */
export function selectEndpoint(current: Endpoints, clicked: LngLat): Endpoints {
    if (current.start && !current.goal) {
        return { start: current.start, goal: clicked };
    }
    return { start: clicked, goal: null };
}
