import { describe, expect, it } from 'vitest';

import type { LngLat } from './kakaoMap';
import type { RouteLine, RouteProgress } from './navigation';
import { findTurns, nextTurn, type Turn } from './turns';

const ORIGIN: LngLat = [126.97, 37.56];
const METERS_PER_DEGREE = (6_371_000 * Math.PI) / 180;

/** 동쪽 x m, 북쪽 y m 지점들을 경로로. 누적 거리는 지점 사이 직선거리 */
function route(...points: [number, number][]): RouteLine {
    const cos = Math.cos((ORIGIN[1] * Math.PI) / 180);
    const coordinates = points.map(([x, y]): LngLat => [
        ORIGIN[0] + x / (METERS_PER_DEGREE * cos),
        ORIGIN[1] + y / METERS_PER_DEGREE,
    ]);
    const distances = [0];
    for (let i = 1; i < points.length; i += 1) {
        const [x1, y1] = points[i - 1];
        const [x2, y2] = points[i];
        distances.push(distances[i - 1] + Math.hypot(x2 - x1, y2 - y1));
    }
    return { coordinates, distances_m: distances };
}

function summary(turns: Turn[]) {
    return turns.map(({ direction, atM, angle }) => ({
        direction,
        atM: Math.round(atM),
        angle: Math.round(angle),
    }));
}

describe('findTurns', () => {
    it('ㄱ자로 꺾이면 꺾이는 곳에서 오른쪽·왼쪽', () => {
        expect(summary(findTurns(route([0, 0], [0, 100], [100, 100])))).toEqual(
            [{ direction: 'right', atM: 100, angle: 90 }],
        );
        expect(
            summary(findTurns(route([0, 0], [0, 100], [-100, 100]))),
        ).toEqual([{ direction: 'left', atM: 100, angle: -90 }]);
    });

    it.each([
        ['30° 는 안내하지 않는다', [58, 200], []],
        ['50° 는 약간', [77, 164], ['slight_right']],
        ['125° 는 크게', [100, 30], ['sharp_right']],
        ['177° 는 유턴', [5, 0], ['uturn']],
    ] as const)('%s', (_, end, expected) => {
        const turns = findTurns(route([0, 0], [0, 100], [end[0], end[1]]));

        expect(turns.map(({ direction }) => direction)).toEqual(expected);
    });

    it('길 모양이 조금 흔들리는 곧은 길은 안내하지 않는다', () => {
        const wiggly = route(
            ...Array.from({ length: 21 }, (_, i): [number, number] => [
                i % 2 === 0 ? 0 : 1.5,
                i * 10,
            ]),
        );

        expect(findTurns(wiggly)).toEqual([]);
    });

    it('휘어진 길은 꺾이는 곳 하나로 합친다', () => {
        // 북쪽으로 50m, 반지름 15m 로 동쪽을 향해 돈 뒤 동쪽으로 50m
        const curve = Array.from({ length: 10 }, (_, i): [number, number] => {
            const theta = (i * 10 * Math.PI) / 180;
            return [15 - 15 * Math.cos(theta), 50 + 15 * Math.sin(theta)];
        });
        const turns = findTurns(route([0, 0], ...curve, [15, 65], [65, 65]));

        expect(turns).toHaveLength(1);
        expect(turns[0].direction).toBe('right');
        expect(turns[0].angle).toBeGreaterThan(75);
        expect(turns[0].atM).toBeGreaterThan(45);
        expect(turns[0].atM).toBeLessThan(75);
    });

    it('반대쪽으로 바로 되꺾이면(인도 비켜 가기) 안내하지 않는다', () => {
        expect(findTurns(route([0, 0], [0, 50], [10, 50], [10, 100]))).toEqual(
            [],
        );
    });

    it('반대쪽으로 꺾는 사이가 멀면 따로 안내한다', () => {
        const zigzag = findTurns(route([0, 0], [0, 50], [30, 50], [30, 100]));

        expect(summary(zigzag)).toEqual([
            { direction: 'right', atM: 50, angle: 90 },
            { direction: 'left', atM: 80, angle: -90 },
        ]);
    });

    it('지점이 둘 이하면 꺾이는 곳이 없다', () => {
        expect(findTurns(route([0, 0], [0, 100]))).toEqual([]);
    });
});

describe('nextTurn', () => {
    const turn = (atM: number): Turn => ({
        atM,
        position: ORIGIN,
        angle: 90,
        direction: 'right',
    });
    const turns = [turn(100), turn(200)];
    const at = (travelledM: number): RouteProgress => ({
        snapped: ORIGIN,
        travelledM,
        remainingM: 300 - travelledM,
        offRouteM: 0,
    });

    it('아직 지나지 않은 첫 회전까지 거리', () => {
        expect(nextTurn(turns, at(40))).toEqual({
            turn: turns[0],
            distanceM: 60,
        });
        expect(nextTurn(turns, at(150))).toEqual({
            turn: turns[1],
            distanceM: 50,
        });
    });

    it('회전을 다 지나면 다음은 도착', () => {
        expect(nextTurn(turns, at(250))).toEqual({
            turn: null,
            distanceM: 50,
        });
    });
});
