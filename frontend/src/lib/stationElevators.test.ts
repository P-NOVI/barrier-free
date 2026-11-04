import { describe, expect, it } from 'vitest';

import type { Elevator } from './elevators';
import type { LngLat } from './kakaoMap';
import {
    elevatorExitsText,
    elevatorStopText,
    needsElevator,
    stationElevators,
    toElevatorEndpoints,
} from './stationElevators';

// 신촌역 2호선 근처. 경도 0.001 은 약 88m
const STATION: LngLat = [126.937, 37.555];

function elevator(id: string, dx: number, exit: string | null): Elevator {
    return {
        id,
        station: '신촌',
        district: '서대문구',
        nodeType: 1,
        position: [STATION[0] + dx, STATION[1]],
        exit,
    };
}

const WEST = elevator('w', -0.001, '6');
const EAST = elevator('e', 0.001, '4');
// 약 700m 떨어진 다른 노선 역 엘리베이터
const FAR = elevator('f', 0.008, '1');
const ELEVATORS = [WEST, EAST, FAR];

describe('needsElevator', () => {
    it('일반 보행·고령자는 역 엘리베이터로 바꾸지 않는다', () => {
        expect(needsElevator('general')).toBe(false);
        expect(needsElevator('elderly')).toBe(false);
    });

    it('휠체어·유모차·목발은 바꾼다', () => {
        expect(needsElevator('manual_wheelchair')).toBe(true);
        expect(needsElevator('power_wheelchair')).toBe(true);
        expect(needsElevator('stroller')).toBe(true);
        expect(needsElevator('crutches')).toBe(true);
    });
});

describe('stationElevators', () => {
    it('역 이름이면 반경 안 엘리베이터만 돌려준다', () => {
        expect(stationElevators('신촌역 2호선', STATION, ELEVATORS)).toEqual([
            WEST,
            EAST,
        ]);
        expect(stationElevators('신촌역', STATION, ELEVATORS)).toHaveLength(2);
        expect(
            stationElevators('신촌역 2호선 부근', STATION, ELEVATORS),
        ).toHaveLength(2);
    });

    it('역 이름이 아니면 빈 배열이다', () => {
        expect(stationElevators('역삼동 123', STATION, ELEVATORS)).toEqual([]);
        expect(stationElevators('강남역점', STATION, ELEVATORS)).toEqual([]);
        expect(stationElevators('현재 위치', STATION, ELEVATORS)).toEqual([]);
    });
});

describe('elevatorExitsText', () => {
    it('출구 번호를 숫자 순서로 겹치지 않게 보인다', () => {
        expect(
            elevatorExitsText([
                elevator('a', 0, '10'),
                WEST,
                elevator('b', 0, '6'),
                elevator('c', 0, null),
                EAST,
            ]),
        ).toBe('엘리베이터: 4번·6번·10번 출구');
    });

    it('출구 번호를 모르면 대수만 보인다', () => {
        expect(elevatorExitsText([elevator('a', 0, null)])).toBe(
            '엘리베이터 1대 (출구 번호 모름)',
        );
    });

    it('엘리베이터가 없으면 null', () => {
        expect(elevatorExitsText([])).toBeNull();
    });
});

describe('toElevatorEndpoints', () => {
    const station = { position: STATION, label: '신촌역 2호선' };

    it('출발역은 도착지에 가장 가까운 엘리베이터로 바꾼다', () => {
        const goal = { position: [126.95, 37.555] as LngLat, label: '집' };
        const { endpoints, stops } = toElevatorEndpoints(
            { start: station, goal },
            'manual_wheelchair',
            ELEVATORS,
        );
        expect(endpoints.start).toEqual({
            ...station,
            position: EAST.position,
        });
        expect(endpoints.goal).toBe(goal);
        expect(stops).toEqual([{ role: 'start', elevator: EAST }]);
    });

    it('도착역은 출발지에 가장 가까운 엘리베이터로 바꾼다', () => {
        const start = { position: [126.92, 37.555] as LngLat, label: '집' };
        const { endpoints } = toElevatorEndpoints(
            { start, goal: station },
            'stroller',
            ELEVATORS,
        );
        expect(endpoints.goal?.position).toEqual(WEST.position);
    });

    it('반대쪽이 없으면 역에 가장 가까운 엘리베이터를 고른다', () => {
        const near = elevator('n', 0.0001, '2');
        const { endpoints } = toElevatorEndpoints(
            { start: station, goal: null },
            'crutches',
            [WEST, near, EAST],
        );
        expect(endpoints.start?.position).toEqual(near.position);
    });

    it('일반 보행이면 그대로 둔다', () => {
        const input = { start: station, goal: null };
        const result = toElevatorEndpoints(input, 'general', ELEVATORS);
        expect(result.endpoints).toBe(input);
        expect(result.stops).toEqual([]);
    });
});

describe('elevatorStopText', () => {
    it('출구 번호가 있으면 함께 보인다', () => {
        expect(elevatorStopText({ role: 'start', elevator: EAST })).toBe(
            '출발: 4번 출구 엘리베이터',
        );
        expect(
            elevatorStopText({
                role: 'goal',
                elevator: elevator('x', 0, null),
            }),
        ).toBe('도착: 엘리베이터');
    });
});
