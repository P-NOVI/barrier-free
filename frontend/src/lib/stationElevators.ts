// 지하철역 엘리베이터. 계단을 못 쓰는 이동 조건이면 역 대신 그 역 엘리베이터로 경로를 찾는다.
import type { Elevator } from './elevators';
import type { LngLat } from './kakaoMap';
import { distanceM } from './navigation';
import type { PresetId } from './presets';
import type { EndpointRole, Endpoints } from './selection';

// "신촌역", "신촌역 2호선", "신촌역 2호선 부근"처럼 '역' 뒤가 끝이거나 띄어쓰기인 이름
const STATION_NAME = /\S역(\s|$)/;
// 역 좌표에서 이 거리 안 엘리베이터를 그 역 것으로 본다.
// 이름이 같은 다른 노선 역(예: 2호선·경의중앙선 신촌역, 약 600m)은 넘지 않는다.
export const STATION_RADIUS_M = 300;
// 계단을 쓸 수 있어 역 엘리베이터로 바꾸지 않는 이동 조건
const STAIRS_OK: readonly PresetId[] = ['general', 'elderly'];

export function needsElevator(preset: PresetId): boolean {
    return !STAIRS_OK.includes(preset);
}

/** name 이 역 이름이면 position 근처 엘리베이터. 역이 아니면 빈 배열 */
export function stationElevators(
    name: string,
    position: LngLat,
    elevators: Elevator[],
): Elevator[] {
    if (!STATION_NAME.test(name)) {
        return [];
    }
    return elevators.filter(
        (elevator) =>
            distanceM(position, elevator.position) <= STATION_RADIUS_M,
    );
}

/** 장소 카드에 보일 문구. 예: "엘리베이터: 4번·6번 출구". 엘리베이터가 없으면 null */
export function elevatorExitsText(elevators: Elevator[]): string | null {
    if (elevators.length === 0) {
        return null;
    }
    const exits = [
        ...new Set(
            elevators
                .map((elevator) => elevator.exit)
                .filter((exit): exit is string => exit !== null),
        ),
    ].sort((a, b) => a.localeCompare(b, 'ko', { numeric: true }));
    if (exits.length === 0) {
        return `엘리베이터 ${elevators.length}대 (출구 번호 모름)`;
    }
    return `엘리베이터: ${exits.map((exit) => `${exit}번`).join('·')} 출구`;
}

export type ElevatorStop = {
    role: EndpointRole;
    elevator: Elevator;
};

const OTHER: Record<EndpointRole, EndpointRole> = {
    start: 'goal',
    goal: 'start',
};

/**
 * 역인 출발·도착을 그 역 엘리베이터로 바꾼다. 엘리베이터가 여럿이면 반대쪽 지점에
 * 가장 가까운 것을 고른다. 반대쪽을 아직 안 골랐으면 역에 가장 가까운 것을 고른다.
 */
export function toElevatorEndpoints(
    endpoints: Endpoints,
    preset: PresetId,
    elevators: Elevator[],
): { endpoints: Endpoints; stops: ElevatorStop[] } {
    if (!needsElevator(preset)) {
        return { endpoints, stops: [] };
    }
    const result: Endpoints = { ...endpoints };
    const stops: ElevatorStop[] = [];
    for (const role of ['start', 'goal'] as const) {
        const endpoint = endpoints[role];
        if (!endpoint) {
            continue;
        }
        const target = endpoints[OTHER[role]]?.position ?? endpoint.position;
        const nearest = nearestTo(
            target,
            stationElevators(endpoint.label, endpoint.position, elevators),
        );
        if (nearest) {
            result[role] = { ...endpoint, position: nearest.position };
            stops.push({ role, elevator: nearest });
        }
    }
    return { endpoints: result, stops };
}

function nearestTo(target: LngLat, elevators: Elevator[]): Elevator | null {
    let best: Elevator | null = null;
    let bestM = Infinity;
    for (const elevator of elevators) {
        const meters = distanceM(target, elevator.position);
        if (meters < bestM) {
            best = elevator;
            bestM = meters;
        }
    }
    return best;
}

/** 경로 패널에 보일 문구. 예: "출발: 4번 출구 엘리베이터" */
export function elevatorStopText({ role, elevator }: ElevatorStop): string {
    const where = elevator.exit ? `${elevator.exit}번 출구 ` : '';
    return `${role === 'start' ? '출발' : '도착'}: ${where}엘리베이터`;
}
