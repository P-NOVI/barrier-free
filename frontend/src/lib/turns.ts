// 백엔드가 찾은 갈림길 회전(경로가 다른 길로 꺾어 들어가는 곳)을 안내 지점으로 만든다.

import type { LngLat } from './kakaoMap';
import type { RouteProgress } from './navigation';
import type { RouteResponse } from './routeApi';

// 꺾는 각도(도)에 따라 '약간', '크게', '유턴'을 붙인다. 안내할 곳은 백엔드가 정한다.
export const TURN_DEG = 60;
export const SHARP_TURN_DEG = 120;
export const UTURN_DEG = 170;

export type TurnDirection =
    | 'left'
    | 'right'
    | 'slight_left'
    | 'slight_right'
    | 'sharp_left'
    | 'sharp_right'
    | 'uturn';

export type Turn = {
    /** 출발점부터 꺾는 갈림길까지 경로를 따라 간 거리(m) */
    atM: number;
    position: LngLat;
    /** 꺾는 각도(도). 오른쪽이 +, 왼쪽이 - */
    angle: number;
    direction: TurnDirection;
};

/** 내 위치에서 다음에 할 일. turn 이 없으면 다음은 도착이다. */
export type NextTurn = {
    turn: Turn | null;
    /** 그 지점까지 경로를 따라 남은 거리(m) */
    distanceM: number;
};

export const DIRECTION_LABELS: Record<TurnDirection, string> = {
    left: '왼쪽',
    right: '오른쪽',
    slight_left: '약간 왼쪽',
    slight_right: '약간 오른쪽',
    sharp_left: '크게 왼쪽',
    sharp_right: '크게 오른쪽',
    uturn: '유턴',
};

function classify(angle: number): TurnDirection {
    const size = Math.abs(angle);
    if (size >= UTURN_DEG) {
        return 'uturn';
    }
    if (size >= SHARP_TURN_DEG) {
        return angle > 0 ? 'sharp_right' : 'sharp_left';
    }
    if (size >= TURN_DEG) {
        return angle > 0 ? 'right' : 'left';
    }
    return angle > 0 ? 'slight_right' : 'slight_left';
}

/** 경로의 갈림길 회전. 출발점에서 가까운 순서다. */
export function routeTurns(
    route: Pick<RouteResponse, 'coordinates' | 'distances_m' | 'turns'>,
): Turn[] {
    return route.turns.map(({ index, angle }) => ({
        atM: route.distances_m[index],
        position: route.coordinates[index],
        angle,
        direction: classify(angle),
    }));
}

/** 지금 진행 위치에서 다음 회전(없으면 도착)과 거기까지 남은 거리 */
export function nextTurn(turns: Turn[], progress: RouteProgress): NextTurn {
    const turn = turns.find(({ atM }) => atM > progress.travelledM) ?? null;
    return {
        turn,
        distanceM: turn ? turn.atM - progress.travelledM : progress.remainingM,
    };
}
