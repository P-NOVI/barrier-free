// POST /api/route 호출. 요청·응답 형식은 backend/app/schemas.py 와 같다.

import { type ApiOptions, requestJson } from './apiClient';
import type { LngLat } from './kakaoMap';
import type { PresetId } from './presets';

export type RouteRequest = {
    start: LngLat;
    goal: LngLat;
    preset: PresetId;
};

/** 경로가 갈림길에서 다른 길로 꺾어 들어가는 곳 */
export type TurnPoint = {
    /** coordinates 에서 몇 번째 지점인지 */
    index: number;
    /** 들어온 방향에서 나가는 방향으로 꺾는 각도(도). 오른쪽이 + */
    angle: number;
};

export type RouteResponse = {
    distance_m: number;
    /** 이동 조건의 평균 속도로 distance_m 을 가는 예상 시간(초) */
    duration_s: number;
    /** 계단을 뺀 구간 중 가장 가파른 |경사| (비율) */
    max_grade: number;
    ascent_m: number;
    steps_count: number;
    coordinates: LngLat[];
    elevations: number[];
    distances_m: number[];
    /** 갈림길에서 다른 길로 꺾어 들어가는 곳. 출발점에서 가까운 순서 */
    turns: TurnPoint[];
    /** 요청한 출발 좌표(출입구를 거치면 그 출입구)에서 경로 시작점까지 거리 */
    start_gap_m: number;
    goal_gap_m: number;
    /** 출발지가 건물·시설 안이라 거친 출입구. 아니면 null */
    start_entrance: LngLat | null;
    goal_entrance: LngLat | null;
};

export function fetchRoute(
    request: RouteRequest,
    options?: ApiOptions,
): Promise<RouteResponse> {
    return requestJson<RouteResponse>(
        {
            path: '/api/route',
            body: request,
            failureMessage: '경로를 찾지 못했습니다.',
        },
        options,
    );
}
