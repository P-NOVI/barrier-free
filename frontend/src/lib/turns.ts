// 경로 좌표에서 꺾이는 지점을 찾아 회전 안내를 만든다.

import type { LngLat } from './kakaoMap';
import {
    closestOnSegment,
    type RouteLine,
    type RouteProgress,
    toLocal,
} from './navigation';

// 경로 선을 이 폭(m) 안에서 곧게 펴서 본다. 길 모양의 작은 흔들림은 꺾임으로 보지 않는다.
const SIMPLIFY_M = 4;
// 같은 쪽으로 이 거리(m) 안에서 이어 꺾이면 휘어진 길 하나로 보고 각도를 합친다.
const MERGE_M = 20;
// 꺾이는 각도(도) 기준: 이보다 덜 꺾이면 안내하지 않는다.
export const SLIGHT_TURN_DEG = 30;
// 이 이상이면 '왼쪽·오른쪽', 그 아래는 '약간 왼쪽·오른쪽'
export const TURN_DEG = 60;
export const UTURN_DEG = 150;

export type TurnDirection =
    'left' | 'right' | 'slight_left' | 'slight_right' | 'uturn';

export type Turn = {
    /** 출발점부터 꺾이는 지점까지 경로를 따라 간 거리(m) */
    atM: number;
    position: LngLat;
    /** 꺾이는 각도(도). 오른쪽이 +, 왼쪽이 - */
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
    uturn: '유턴',
};

type Point = [number, number];

/** 북쪽에서 시계 방향 각도(도) */
function heading([x1, y1]: Point, [x2, y2]: Point): number {
    return (Math.atan2(x2 - x1, y2 - y1) * 180) / Math.PI;
}

/** -180 ~ 180 */
function normalize(angle: number): number {
    return ((((angle + 180) % 360) + 360) % 360) - 180;
}

/** 더글러스-푀커로 남길 지점 번호 */
function simplify(points: Point[], tolerance: number): number[] {
    const keep = new Set([0, points.length - 1]);
    const ranges: [number, number][] = [[0, points.length - 1]];
    for (let range = ranges.pop(); range; range = ranges.pop()) {
        const [first, last] = range;
        let farthest = -1;
        let farthestDistance = tolerance;
        for (let i = first + 1; i < last; i += 1) {
            const [x, y] = points[i];
            const { distance } = closestOnSegment(
                [points[first][0] - x, points[first][1] - y],
                [points[last][0] - x, points[last][1] - y],
            );
            if (distance > farthestDistance) {
                farthest = i;
                farthestDistance = distance;
            }
        }
        if (farthest >= 0) {
            keep.add(farthest);
            ranges.push([first, farthest], [farthest, last]);
        }
    }
    return [...keep].sort((a, b) => a - b);
}

function classify(angle: number): TurnDirection | null {
    const size = Math.abs(angle);
    if (size >= UTURN_DEG) {
        return 'uturn';
    }
    if (size >= TURN_DEG) {
        return angle > 0 ? 'right' : 'left';
    }
    if (size >= SLIGHT_TURN_DEG) {
        return angle > 0 ? 'slight_right' : 'slight_left';
    }
    return null;
}

/** 경로에서 안내할 만큼 꺾이는 지점들. 출발점에서 가까운 순서다. */
export function findTurns(route: RouteLine): Turn[] {
    const { coordinates, distances_m: distances } = route;
    if (coordinates.length < 3) {
        return [];
    }
    const points = coordinates.map((point) => toLocal(point, coordinates[0]));
    // 같은 자리에 겹친 지점은 방향을 정할 수 없어 뺀다.
    const kept = simplify(points, SIMPLIFY_M).filter(
        (index, i, all) =>
            i === 0 ||
            Math.hypot(
                points[index][0] - points[all[i - 1]][0],
                points[index][1] - points[all[i - 1]][1],
            ) > 0,
    );

    const corners: { index: number; angle: number }[] = [];
    for (let i = 1; i + 1 < kept.length; i += 1) {
        const [before, at, after] = [kept[i - 1], kept[i], kept[i + 1]];
        const angle = normalize(
            heading(points[at], points[after]) -
                heading(points[before], points[at]),
        );
        const last = corners[corners.length - 1];
        const merge =
            last &&
            Math.sign(last.angle) === Math.sign(angle) &&
            distances[at] - distances[last.index] < MERGE_M;
        if (merge) {
            // 휘어진 길은 꺾이기 시작하는 곳을 안내 지점으로 둔다.
            last.angle += angle;
        } else {
            corners.push({ index: at, angle });
        }
    }

    return corners.flatMap(({ index, angle }) => {
        const direction = classify(angle);
        return direction
            ? [
                  {
                      atM: distances[index],
                      position: coordinates[index],
                      angle,
                      direction,
                  },
              ]
            : [];
    });
}

/** 지금 진행 위치에서 다음 회전(없으면 도착)과 거기까지 남은 거리 */
export function nextTurn(turns: Turn[], progress: RouteProgress): NextTurn {
    const turn = turns.find(({ atM }) => atM > progress.travelledM) ?? null;
    return {
        turn,
        distanceM: turn ? turn.atM - progress.travelledM : progress.remainingM,
    };
}
