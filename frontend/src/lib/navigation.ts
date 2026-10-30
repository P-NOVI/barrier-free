// 경로를 따라 걸을 때 내 위치가 경로 어디쯤인지, 벗어났는지 판단한다.

import type { LngLat } from './kakaoMap';

// backend/core/snap.py 와 같은 지구 반지름
const EARTH_RADIUS_M = 6_371_000;
const METERS_PER_DEGREE = (EARTH_RADIUS_M * Math.PI) / 180;

// 경로 선에서 이보다 멀면 벗어난 것으로 본다. 위치 오차가 더 크면 오차만큼 봐준다.
export const OFF_ROUTE_M = 25;
// 경로 끝까지 이만큼 남으면 도착
export const ARRIVAL_M = 20;
// 오차가 이보다 큰 위치로는 이탈·도착을 판단하지 않는다 (실내, Wi-Fi 기반 위치 등).
export const MAX_ACCURACY_M = 50;
// 이 횟수만큼 연달아 벗어나야 경로를 다시 찾는다. 위치가 한 번 튀는 것은 넘긴다.
export const OFF_ROUTE_FIXES = 2;
// 다시 찾은 곳에서 이만큼 움직이기 전에는 또 찾지 않는다.
// 길이 없는 곳(건물 안 등)에서 같은 요청을 되풀이하지 않게 한다.
export const REROUTE_MIN_MOVE_M = 30;

/** 따라갈 경로. 경로 응답의 coordinates, distances_m 과 같다. */
export type RouteLine = {
    coordinates: LngLat[];
    /** 출발점부터 각 지점까지 누적 거리(m) */
    distances_m: number[];
};

export type RouteProgress = {
    /** 경로 선 위에서 내 위치와 가장 가까운 점 */
    snapped: LngLat;
    /** 출발점부터 snapped 까지 경로를 따라 간 거리(m) */
    travelledM: number;
    /** snapped 부터 경로 끝까지 남은 거리(m) */
    remainingM: number;
    /** 내 위치와 경로 선 사이 거리(m) */
    offRouteM: number;
};

export type Judgement = 'on_route' | 'off_route' | 'arrived' | 'uncertain';

export type RerouteTracker = {
    /** 연달아 경로를 벗어난 위치 수 */
    offRouteFixes: number;
    /** 마지막으로 경로를 다시 찾은 곳 */
    reroutedAt: LngLat | null;
};

export const NEW_TRACKER: RerouteTracker = {
    offRouteFixes: 0,
    reroutedAt: null,
};

/** 두 좌표 사이 거리(m). 걷는 거리 안에서는 평면으로 봐도 오차가 작다. */
export function distanceM(a: LngLat, b: LngLat): number {
    const [x, y] = toLocal(b, a);
    return Math.hypot(x, y);
}

/** origin 기준 동쪽·북쪽 m */
export function toLocal(
    [lng, lat]: LngLat,
    [lng0, lat0]: LngLat,
): [number, number] {
    const cos = Math.cos((lat0 * Math.PI) / 180);
    return [
        (lng - lng0) * METERS_PER_DEGREE * cos,
        (lat - lat0) * METERS_PER_DEGREE,
    ];
}

/**
 * 원점에서 선분 AB 위 가장 가까운 점 A + t(B - A) 의 t(0~1)와 거리.
 * a, b 는 원점 기준 평면 좌표(m)다.
 */
export function closestOnSegment(
    [ax, ay]: [number, number],
    [bx, by]: [number, number],
): { t: number; distance: number } {
    const dx = bx - ax;
    const dy = by - ay;
    const lengthSquared = dx * dx + dy * dy;
    const t =
        lengthSquared === 0
            ? 0
            : Math.min(1, Math.max(0, -(ax * dx + ay * dy) / lengthSquared));
    return { t, distance: Math.hypot(ax + t * dx, ay + t * dy) };
}

/** 내 위치를 경로 선 위 가장 가까운 점에 맞춰 진행 정도를 계산한다. */
export function progressAlong(
    route: RouteLine,
    position: LngLat,
): RouteProgress {
    const { coordinates, distances_m: distances } = route;
    const total = distances[distances.length - 1];
    let best = {
        snapped: coordinates[0],
        travelledM: 0,
        offRouteM: distanceM(position, coordinates[0]),
    };
    for (let i = 0; i + 1 < coordinates.length; i += 1) {
        // 내 위치를 원점으로 두고 구간 위 가장 가까운 점을 찾는다.
        const { t, distance: offRouteM } = closestOnSegment(
            toLocal(coordinates[i], position),
            toLocal(coordinates[i + 1], position),
        );
        if (offRouteM < best.offRouteM) {
            const [lng1, lat1] = coordinates[i];
            const [lng2, lat2] = coordinates[i + 1];
            best = {
                snapped: [lng1 + t * (lng2 - lng1), lat1 + t * (lat2 - lat1)],
                travelledM:
                    distances[i] + t * (distances[i + 1] - distances[i]),
                offRouteM,
            };
        }
    }
    return { ...best, remainingM: total - best.travelledM };
}

/** 오차 반경이 accuracy 인 위치가 경로를 따라가는 중인지, 벗어났는지, 도착했는지 */
export function judge(progress: RouteProgress, accuracy: number): Judgement {
    if (accuracy > MAX_ACCURACY_M) {
        return 'uncertain';
    }
    if (progress.offRouteM > Math.max(OFF_ROUTE_M, accuracy)) {
        return 'off_route';
    }
    return progress.remainingM <= ARRIVAL_M ? 'arrived' : 'on_route';
}

/** 새 위치의 판단을 반영하고, 지금 경로를 다시 찾아야 하는지 알려 준다. */
export function trackOffRoute(
    tracker: RerouteTracker,
    judgement: Judgement,
    position: LngLat,
): { tracker: RerouteTracker; reroute: boolean } {
    if (judgement === 'uncertain') {
        return { tracker, reroute: false };
    }
    const offRouteFixes =
        judgement === 'off_route' ? tracker.offRouteFixes + 1 : 0;
    const movedAway =
        !tracker.reroutedAt ||
        distanceM(tracker.reroutedAt, position) >= REROUTE_MIN_MOVE_M;
    if (offRouteFixes >= OFF_ROUTE_FIXES && movedAway) {
        return {
            tracker: { offRouteFixes: 0, reroutedAt: position },
            reroute: true,
        };
    }
    return { tracker: { ...tracker, offRouteFixes }, reroute: false };
}
