import { describe, expect, it } from 'vitest';

import type { LngLat } from './kakaoMap';
import type { RouteProgress } from './navigation';
import { nextTurn, routeTurns, type Turn } from './turns';

const ORIGIN: LngLat = [126.97, 37.56];

describe('routeTurns', () => {
    const coordinates: LngLat[] = [
        [126.97, 37.56],
        [126.97, 37.561],
        [126.971, 37.561],
        [126.971, 37.562],
    ];
    const distances = [0, 111, 199, 310];

    it('갈림길 지점의 거리·좌표와 방향을 붙인다', () => {
        const turns = routeTurns({
            coordinates,
            distances_m: distances,
            turns: [
                { index: 1, angle: 90 },
                { index: 2, angle: -88 },
            ],
        });

        expect(turns).toEqual([
            {
                atM: 111,
                position: coordinates[1],
                angle: 90,
                direction: 'right',
            },
            {
                atM: 199,
                position: coordinates[2],
                angle: -88,
                direction: 'left',
            },
        ]);
    });

    it.each([
        [25, 'slight_right'],
        [-59, 'slight_left'],
        [60, 'right'],
        [-125, 'sharp_left'],
        [177, 'uturn'],
        [-170, 'uturn'],
    ] as const)('%d° 는 %s', (angle, direction) => {
        const [turn] = routeTurns({
            coordinates,
            distances_m: distances,
            turns: [{ index: 1, angle }],
        });

        expect(turn.direction).toBe(direction);
    });

    it('갈림길에서 꺾지 않는 경로는 회전이 없다', () => {
        expect(
            routeTurns({ coordinates, distances_m: distances, turns: [] }),
        ).toEqual([]);
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
