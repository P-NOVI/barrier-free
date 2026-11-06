import { describe, expect, it } from 'vitest';

import type { LngLat } from './kakaoMap';
import { toLocal } from './navigation';
import { smoothJogs } from './routeShape';

const ORIGIN: LngLat = [127.0, 37.5];
const METERS_PER_DEGREE = (6_371_000 * Math.PI) / 180;

/** ORIGIN 에서 동쪽 x m, 북쪽 y m */
function meters(x: number, y: number): LngLat {
    const cos = Math.cos((ORIGIN[1] * Math.PI) / 180);
    return [
        ORIGIN[0] + x / (METERS_PER_DEGREE * cos),
        ORIGIN[1] + y / METERS_PER_DEGREE,
    ];
}

function path(...points: [number, number][]): LngLat[] {
    return points.map(([x, y]) => meters(x, y));
}

function inMeters(shape: LngLat[]): [number, number][] {
    return shape.map((point) => {
        const [x, y] = toLocal(point, ORIGIN);
        return [Math.round(x * 10) / 10, Math.round(y * 10) / 10];
    });
}

describe('smoothJogs', () => {
    it('교차로에서 직각으로 꺾는 곳은 그대로 둔다', () => {
        const turn = path([0, 0], [40, 0], [40, 40], [80, 40]);

        expect(smoothJogs(turn)).toEqual(turn);
    });

    it('횡단보도를 직각으로 건너는 곳은 그대로 둔다', () => {
        const crossing = path([0, 0], [30, 0], [30, -20], [60, -20]);

        expect(smoothJogs(crossing)).toEqual(crossing);
    });

    it('지나쳤다가 비스듬히 되돌아오는 곳은 앞뒤 5m 에서 대각선으로 잇는다', () => {
        const overshoot = path([0, 0], [30, 0], [22, -20], [60, -20]);

        expect(inMeters(smoothJogs(overshoot))).toEqual([
            [0, 0],
            [25, 0],
            [27, -20],
            [60, -20],
        ]);
    });

    it('비스듬히 살짝 비켜나는 곳도 대각선으로 잇는다', () => {
        const jog = path([0, 0], [30, 0], [34, -4], [64, -4]);

        expect(inMeters(smoothJogs(jog))).toEqual([
            [0, 0],
            [25, 0],
            [39, -4],
            [64, -4],
        ]);
    });

    it('대각선 시작점은 앞뒤 직선 길이의 절반을 넘지 않는다', () => {
        const jog = path([0, 0], [6, 0], [10, -4], [14, -4]);

        expect(inMeters(smoothJogs(jog))).toEqual([
            [0, 0],
            [3, 0],
            [12, -4],
            [14, -4],
        ]);
    });

    it('꺾인 구간이 길면 그대로 둔다', () => {
        const long = path([0, 0], [30, 0], [10, -30], [60, -30]);

        expect(smoothJogs(long)).toEqual(long);
    });

    it('꺾였다가 다른 방향으로 나가면 그대로 둔다', () => {
        const turn = path([0, 0], [30, 0], [36, -6], [36, -40]);

        expect(smoothJogs(turn)).toEqual(turn);
    });

    it('같은 점이 이어지면 하나만 남기고 처음과 끝 점은 그대로다', () => {
        const route = path([0, 0], [0, 0], [30, 0], [30, 0], [60, 0]);

        expect(smoothJogs(route)).toEqual(path([0, 0], [30, 0], [60, 0]));
    });
});
