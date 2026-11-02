import { describe, expect, it } from 'vitest';

import type { LngLat } from './kakaoMap';
import {
    distanceM,
    judge,
    NEW_TRACKER,
    progressAlong,
    type RouteProgress,
    type RouteLine,
    trackOffRoute,
} from './navigation';

// ㄱ자 경로: A 에서 동쪽으로 B, B 에서 북쪽으로 C.
// 누적 거리는 경로 응답처럼 실제 길 길이라 좌표 사이 직선거리와 다를 수 있다.
const A: LngLat = [126.97, 37.56];
const B: LngLat = [126.971, 37.56];
const C: LngLat = [126.971, 37.561];
const ROUTE: RouteLine = { coordinates: [A, B, C], distances_m: [0, 100, 300] };

// 위도 37.56 에서 경도 0.0001° ≈ 8.8m, 위도 0.0001° ≈ 11.1m
const north = ([lng, lat]: LngLat, meters: number): LngLat => [
    lng,
    lat + meters / 111_195,
];

function progress(offRouteM: number, remainingM: number): RouteProgress {
    return { snapped: A, travelledM: 0, offRouteM, remainingM };
}

describe('distanceM', () => {
    it('남북 1° 는 약 111km', () => {
        expect(distanceM([127, 37], [127, 38])).toBeCloseTo(111_195, -1);
    });
});

describe('progressAlong', () => {
    it('경로 위 위치는 그 자리의 누적 거리를 비율로 나눠 쓴다', () => {
        const result = progressAlong(ROUTE, [126.9705, 37.56]);

        expect(result.offRouteM).toBeCloseTo(0, 6);
        expect(result.travelledM).toBeCloseTo(50, 6);
        expect(result.remainingM).toBeCloseTo(250, 6);
        expect(result.snapped[0]).toBeCloseTo(126.9705, 9);
    });

    it('경로 옆 위치는 가장 가까운 구간에 맞추고 떨어진 거리를 잰다', () => {
        const result = progressAlong(ROUTE, north([126.9705, 37.56], 10));

        expect(result.offRouteM).toBeCloseTo(10, 3);
        expect(result.travelledM).toBeCloseTo(50, 3);
        expect(result.snapped[1]).toBeCloseTo(37.56, 9);
    });

    it('두 번째 구간 옆이면 두 번째 구간에서 잰다', () => {
        const result = progressAlong(ROUTE, [126.97105, 37.5605]);

        expect(result.travelledM).toBeCloseTo(200, 3);
        expect(result.offRouteM).toBeCloseTo(4.4, 1);
    });

    it('출발점 앞이면 출발점, 끝을 지나면 끝점에 맞춘다', () => {
        const before = progressAlong(ROUTE, [126.9695, 37.56]);
        const after = progressAlong(ROUTE, north(C, 30));

        expect(before.snapped).toEqual(A);
        expect(before.travelledM).toBe(0);
        expect(after.snapped[1]).toBeCloseTo(C[1], 9);
        expect(after.remainingM).toBeCloseTo(0, 6);
        expect(after.offRouteM).toBeCloseTo(30, 3);
    });

    it('지점이 하나뿐인 경로(출발 = 도착)', () => {
        const result = progressAlong(
            { coordinates: [A], distances_m: [0] },
            north(A, 5),
        );

        expect(result.remainingM).toBe(0);
        expect(result.offRouteM).toBeCloseTo(5, 3);
    });
});

describe('judge', () => {
    it.each([
        ['오차가 크면 판단하지 않는다', progress(100, 200), 80, 'uncertain'],
        ['경로에서 멀면 이탈', progress(30, 200), 10, 'off_route'],
        ['오차 안이면 이탈로 보지 않는다', progress(30, 200), 40, 'on_route'],
        ['끝이 가까우면 도착', progress(5, 15), 10, 'arrived'],
        ['끝이 가까워도 경로에서 멀면 이탈', progress(40, 15), 10, 'off_route'],
    ] as const)('%s', (_, given, accuracy, expected) => {
        expect(judge(given, accuracy)).toBe(expected);
    });
});

describe('trackOffRoute', () => {
    const here: LngLat = [126.97, 37.56];

    it('연달아 두 번 벗어나면 다시 찾는다', () => {
        const first = trackOffRoute(NEW_TRACKER, 'off_route', here);
        const second = trackOffRoute(first.tracker, 'off_route', here);

        expect(first.reroute).toBe(false);
        expect(second.reroute).toBe(true);
        expect(second.tracker).toEqual({ offRouteFixes: 0, reroutedAt: here });
    });

    it('사이에 경로로 돌아오면 다시 센다', () => {
        let tracker = trackOffRoute(NEW_TRACKER, 'off_route', here).tracker;
        tracker = trackOffRoute(tracker, 'on_route', here).tracker;
        const result = trackOffRoute(tracker, 'off_route', here);

        expect(result.reroute).toBe(false);
        expect(result.tracker.offRouteFixes).toBe(1);
    });

    it('오차가 큰 위치는 세지도, 다시 세게 하지도 않는다', () => {
        let tracker = trackOffRoute(NEW_TRACKER, 'off_route', here).tracker;
        tracker = trackOffRoute(tracker, 'uncertain', here).tracker;

        expect(trackOffRoute(tracker, 'off_route', here).reroute).toBe(true);
    });

    it('다시 찾은 곳에서 충분히 움직이기 전에는 또 찾지 않는다', () => {
        // 한 번 벗어난 상태에서 또 벗어남
        const tracker = { offRouteFixes: 1, reroutedAt: here };

        expect(
            trackOffRoute(tracker, 'off_route', north(here, 10)).reroute,
        ).toBe(false);
        expect(
            trackOffRoute(tracker, 'off_route', north(here, 40)).reroute,
        ).toBe(true);
    });
});
