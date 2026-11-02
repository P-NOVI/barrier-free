// POST /api/route 호출. 요청·응답 형식은 backend/app/schemas.py 와 같다.

import type { LngLat } from './kakaoMap';
import type { PresetId } from './presets';

export type RouteRequest = {
    start: LngLat;
    goal: LngLat;
    preset: PresetId;
};

export type RouteResponse = {
    distance_m: number;
    /** 계단을 뺀 구간 중 가장 가파른 |경사| (비율) */
    max_grade: number;
    ascent_m: number;
    steps_count: number;
    coordinates: LngLat[];
    elevations: number[];
    distances_m: number[];
    /** 요청한 출발 좌표에서 경로 시작점까지 거리 */
    start_gap_m: number;
    goal_gap_m: number;
};

/** reason 은 백엔드 detail.reason (start_off_network, no_path 등) 또는 config · network · http */
export class RouteError extends Error {
    readonly reason: string;

    constructor(message: string, reason: string) {
        super(message);
        this.name = 'RouteError';
        this.reason = reason;
    }
}

function isRecord(value: unknown): value is Record<string, unknown> {
    return typeof value === 'object' && value !== null;
}

async function toRouteError(response: Response): Promise<RouteError> {
    const body: unknown = await response.json().catch(() => null);
    const detail = isRecord(body) ? body.detail : undefined;
    if (
        isRecord(detail) &&
        typeof detail.message === 'string' &&
        typeof detail.reason === 'string'
    ) {
        return new RouteError(detail.message, detail.reason);
    }
    return new RouteError(
        `경로를 찾지 못했습니다. (HTTP ${response.status})`,
        'http',
    );
}

export async function fetchRoute(
    request: RouteRequest,
    {
        baseUrl = import.meta.env.VITE_API_BASE_URL,
        signal,
    }: { baseUrl?: string; signal?: AbortSignal } = {},
): Promise<RouteResponse> {
    if (!baseUrl) {
        throw new RouteError(
            'VITE_API_BASE_URL 이 없습니다. frontend/.env 를 확인하세요.',
            'config',
        );
    }
    let response: Response;
    try {
        response = await fetch(new URL('/api/route', baseUrl), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(request),
            signal,
        });
    } catch (error) {
        if (signal?.aborted) {
            throw error;
        }
        throw new RouteError(
            '경로 서버에 연결하지 못했습니다. 백엔드가 켜져 있는지 확인하세요.',
            'network',
        );
    }
    if (!response.ok) {
        throw await toRouteError(response);
    }
    return (await response.json()) as RouteResponse;
}
