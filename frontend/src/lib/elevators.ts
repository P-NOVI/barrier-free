// 지하철역 엘리베이터 위치 데이터. 지금은 정적 JSON 을 읽고,
// 백엔드 /api/elevators 가 생기면 DEFAULT_URL 만 바꾼다.
import type { LngLat } from './kakaoMap';

const DEFAULT_URL = '/data/elevators.json';

export type Elevator = {
    id: string;
    // 역명이 비어 있는 엘리베이터가 있다
    station: string;
    district: string;
    nodeType: number;
    position: LngLat;
};

/** 지도 마커와 장소 카드에 보일 이름. 예: "강남역 엘리베이터". 역명이 없으면 "엘리베이터" */
export function elevatorName(elevator: Elevator): string {
    return elevator.station ? `${elevator.station} 엘리베이터` : '엘리베이터';
}

function isRecord(value: unknown): value is Record<string, unknown> {
    return typeof value === 'object' && value !== null;
}

function isLngLat(value: unknown): value is LngLat {
    return (
        Array.isArray(value) &&
        value.length === 2 &&
        value.every((n) => typeof n === 'number' && Number.isFinite(n))
    );
}

export function parseElevators(data: unknown): Elevator[] {
    if (!Array.isArray(data)) {
        throw new Error('엘리베이터 데이터가 배열이 아닙니다.');
    }
    return data.map((item, index) => {
        if (
            !isRecord(item) ||
            typeof item.id !== 'string' ||
            typeof item.station !== 'string' ||
            typeof item.district !== 'string' ||
            typeof item.nodeType !== 'number' ||
            !isLngLat(item.position)
        ) {
            throw new Error(`엘리베이터 ${index}번 항목 형식이 다릅니다.`);
        }
        return {
            id: item.id,
            station: item.station,
            district: item.district,
            nodeType: item.nodeType,
            position: item.position,
        };
    });
}

export async function fetchElevators(url = DEFAULT_URL): Promise<Elevator[]> {
    const response = await fetch(url);
    if (!response.ok) {
        throw new Error(
            `엘리베이터 데이터를 불러오지 못했습니다. (${response.status})`,
        );
    }
    return parseElevators(await response.json());
}
