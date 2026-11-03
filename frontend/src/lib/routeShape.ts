// 화면에 그리는 경로 선 모양을 다듬는다. 꺾는 곳 안내·남은 거리는 원래 좌표로 계산한다.
//
// 경로가 짧은 거리 안에서 이리저리 꺾였다가 원래 방향으로 돌아오는 곳(S자 꺾임)이 있다.
// 횡단보도를 비스듬히 건너 지나쳤다가 되돌아오는 곳처럼 화면에서 어색하게 보여서 그 구간을
// 대각선 하나로 잇는다. 아래는 그대로 둔다.
// - 교차로에서 다른 길로 꺾는 곳: 나가는 방향이 들어온 방향과 달라서 S자가 아니다.
// - 횡단보도를 똑바로 건너는 곳: 직각으로 두 번 꺾여서 도로 각도대로 보인다.

import type { LngLat } from './kakaoMap';
import { distanceM, toLocal } from './navigation';

// S자 꺾임으로 보는 범위
// 처음 꺾인 곳부터 마지막 꺾인 곳까지 길이(m)
export const JOG_MAX_LENGTH_M = 35;
// 들어온 직선에서 옆으로 비켜난 거리(m)
export const JOG_MAX_OFFSET_M = 30;
// 들어온 방향과 나가는 방향의 차이(도)
export const JOG_MAX_NET_TURN_DEG = 45;
// 이보다 덜 꺾인 곳은 꺾인 곳으로 보지 않는다(도).
export const JOG_MIN_TURN_DEG = 30;
// 꺾인 곳이 모두 직각에서 이 각도 안이면 도로 각도대로 꺾인 것으로 보고 그대로 둔다(도).
export const RIGHT_ANGLE_TOLERANCE_DEG = 15;
// 꺾인 곳 앞뒤 직선에서 대각선이 시작하는 거리(m). 그 직선 길이의 절반을 넘지 않는다.
export const JOG_CUT_M = 5;

type Vector = [number, number];

/** S자 꺾임을 대각선으로 이은 선. 처음과 끝 점은 그대로다. */
export function smoothJogs(path: LngLat[]): LngLat[] {
    const points = path.filter(
        (point, i) =>
            i === 0 ||
            point[0] !== path[i - 1][0] ||
            point[1] !== path[i - 1][1],
    );
    if (points.length < 4) {
        return points;
    }
    const shape: LngLat[] = [points[0]];
    let i = 1;
    while (i < points.length - 1) {
        const before = shape[shape.length - 1];
        const end = jogEnd(points, before, i);
        if (end === null) {
            shape.push(points[i]);
            i += 1;
            continue;
        }
        shape.push(
            cutBack(points[i], before),
            cutBack(points[end], points[end + 1]),
        );
        i = end + 1;
    }
    shape.push(points[points.length - 1]);
    return shape;
}

/** before → points[i] 로 들어와 points[i] 에서 꺾이기 시작하는 S자 꺾임의 마지막 꺾인 점 번호. */
function jogEnd(points: LngLat[], before: LngLat, i: number): number | null {
    const origin = points[i];
    const incoming = direction(before, origin);
    const first = turnDeg(incoming, direction(origin, points[i + 1]));
    if (first < JOG_MIN_TURN_DEG) {
        return null;
    }
    const turns = [first];
    let length = 0;
    for (let j = i + 1; j < points.length - 1; j++) {
        length += distanceM(points[j - 1], points[j]);
        if (
            length > JOG_MAX_LENGTH_M ||
            offsetM(incoming, toLocal(points[j], origin)) > JOG_MAX_OFFSET_M
        ) {
            return null;
        }
        const outgoing = direction(points[j], points[j + 1]);
        const turn = turnDeg(direction(points[j - 1], points[j]), outgoing);
        if (turn < JOG_MIN_TURN_DEG) {
            continue;
        }
        turns.push(turn);
        if (turnDeg(incoming, outgoing) <= JOG_MAX_NET_TURN_DEG) {
            return turns.every(isRightAngle) ? null : j;
        }
    }
    return null;
}

function isRightAngle(turn: number): boolean {
    return Math.abs(turn - 90) <= RIGHT_ANGLE_TOLERANCE_DEG;
}

/** corner 에서 toward 쪽으로 JOG_CUT_M(직선 절반까지) 간 점 */
function cutBack(corner: LngLat, toward: LngLat): LngLat {
    const length = distanceM(corner, toward);
    const ratio = Math.min(JOG_CUT_M, length / 2) / length;
    return [
        corner[0] + (toward[0] - corner[0]) * ratio,
        corner[1] + (toward[1] - corner[1]) * ratio,
    ];
}

function direction(from: LngLat, to: LngLat): Vector {
    const [x, y] = toLocal(to, from);
    const length = Math.hypot(x, y);
    return [x / length, y / length];
}

/** 두 방향 사이 각도(0~180도) */
function turnDeg(a: Vector, b: Vector): number {
    const cos = Math.max(-1, Math.min(1, a[0] * b[0] + a[1] * b[1]));
    return (Math.acos(cos) * 180) / Math.PI;
}

/** 방향 along 으로 그은 직선에서 offset 이 옆으로 떨어진 거리(m) */
function offsetM(along: Vector, offset: Vector): number {
    return Math.abs(along[0] * offset[1] - along[1] * offset[0]);
}
