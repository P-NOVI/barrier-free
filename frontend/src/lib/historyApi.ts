// 검색·경로 이력. 쿠키의 사용자(게스트·회원) 것만 오간다.
// 요청·응답 형식은 backend/app/schemas.py 의 SearchHistory*, RouteHistory* 와 같다.

import { type ApiOptions, requestJson } from './apiClient';
import type { LngLat } from './kakaoMap';
import type { Place } from './placeApi';
import type { PresetId } from './presets';
import {
    CURRENT_LOCATION_LABEL,
    type Endpoint,
    type Endpoints,
} from './selection';

// backend/app/models.py 의 QUERY_MAX_LENGTH 와 같다.
const QUERY_MAX_LENGTH = 100;

export type SearchHistoryRequest = {
    /** 입력한 검색어 */
    query: string;
    /** 검색 결과에서 고른 장소 */
    place_name: string | null;
    address: string | null;
    position: LngLat | null;
};

export type SearchHistory = SearchHistoryRequest & {
    id: number;
    created_at: string;
};

export type RouteHistoryRequest = {
    start_name: string;
    start: LngLat;
    goal_name: string;
    goal: LngLat;
    preset: PresetId;
    distance_m: number;
};

export type RouteHistory = Omit<RouteHistoryRequest, 'preset'> & {
    id: number;
    /** 예전에 저장한 값일 수 있어 PresetId 로 좁히지 않는다. */
    preset: string;
    created_at: string;
};

// 쿠키가 없으면 처음 저장할 때 게스트가 만들어진다.
// 두 저장이 동시에 가면 게스트가 둘 생기므로, 앞 저장의 쿠키를 받은 뒤에 다음을 보낸다.
// 즐겨찾기·내 장소 저장(savedPlacesApi.ts)도 이 순서를 따른다.
let lastWrite: Promise<unknown> = Promise.resolve();

export function inOrder<T>(send: () => Promise<T>): Promise<T> {
    const result = lastWrite.then(send, send);
    lastWrite = result.catch(() => undefined);
    return result;
}

export async function fetchSearches(
    options?: ApiOptions,
): Promise<SearchHistory[]> {
    const { searches } = await requestJson<{ searches: SearchHistory[] }>(
        {
            path: '/api/me/searches',
            failureMessage: '최근 검색을 불러오지 못했습니다.',
        },
        options,
    );
    return searches;
}

/** 같은 검색을 다시 저장하면 새로 쌓지 않고 맨 앞으로 옮긴다. */
export function addSearch(
    entry: SearchHistoryRequest,
    options?: ApiOptions,
): Promise<SearchHistory> {
    return inOrder(() =>
        requestJson<SearchHistory>(
            {
                path: '/api/me/searches',
                body: entry,
                failureMessage: '검색 기록을 남기지 못했습니다.',
            },
            options,
        ),
    );
}

export function deleteSearch(id: number, options?: ApiOptions): Promise<void> {
    return inOrder(() =>
        requestJson<void>(
            {
                path: `/api/me/searches/${id}`,
                method: 'DELETE',
                failureMessage: '검색 기록을 지우지 못했습니다.',
            },
            options,
        ),
    );
}

export async function fetchRoutes(
    options?: ApiOptions,
): Promise<RouteHistory[]> {
    const { routes } = await requestJson<{ routes: RouteHistory[] }>(
        {
            path: '/api/me/routes',
            failureMessage: '최근 경로를 불러오지 못했습니다.',
        },
        options,
    );
    return routes;
}

/** 같은 출발·도착·프리셋이면 새로 쌓지 않고 맨 앞으로 옮긴다. */
export function addRoute(
    entry: RouteHistoryRequest,
    options?: ApiOptions,
): Promise<RouteHistory> {
    return inOrder(() =>
        requestJson<RouteHistory>(
            {
                path: '/api/me/routes',
                body: entry,
                failureMessage: '경로 기록을 남기지 못했습니다.',
            },
            options,
        ),
    );
}

export function deleteRoute(id: number, options?: ApiOptions): Promise<void> {
    return inOrder(() =>
        requestJson<void>(
            {
                path: `/api/me/routes/${id}`,
                method: 'DELETE',
                failureMessage: '경로 기록을 지우지 못했습니다.',
            },
            options,
        ),
    );
}

/** 검색어 query 로 찾아 place 를 고른 기록. 검색어가 비면 장소 이름을 쓴다. */
export function toSearchEntry(
    query: string,
    place: Place,
): SearchHistoryRequest {
    return {
        query: (query.trim() || place.name).slice(0, QUERY_MAX_LENGTH),
        place_name: place.name,
        address: place.road_address || place.address || null,
        position: place.position,
    };
}

/** 장소를 고른 기록만 다시 고를 수 있다. */
export function searchEndpoint(entry: SearchHistory): Endpoint | null {
    if (!entry.position) {
        return null;
    }
    return { position: entry.position, label: entry.place_name ?? entry.query };
}

/** 같은 장소는 가장 최근 것 하나만 두고 limit 개까지 */
export function recentPlaces(
    searches: SearchHistory[],
    limit: number,
): SearchHistory[] {
    const seen = new Set<string>();
    return searches
        .filter((entry) => {
            if (!entry.position) {
                return false;
            }
            const key = String(entry.position);
            if (seen.has(key)) {
                return false;
            }
            seen.add(key);
            return true;
        })
        .slice(0, limit);
}

/** 출발·도착이 다 정해졌을 때만 기록을 만든다. */
export function toRouteEntry(
    endpoints: Endpoints,
    preset: PresetId,
    distance_m: number,
): RouteHistoryRequest | null {
    const { start, goal } = endpoints;
    if (!start || !goal) {
        return null;
    }
    return {
        start_name: start.label,
        start: start.position,
        goal_name: goal.label,
        goal: goal.position,
        preset,
        distance_m,
    };
}

/**
 * 경로 기록을 다시 고를 때의 출발·도착.
 * '현재 위치'에서 출발한 기록은 그때 자리가 지금 위치가 아니므로 출발지를 null 로 둔다.
 */
export function routeEndpoints(entry: RouteHistory): {
    start: Endpoint | null;
    goal: Endpoint;
} {
    return {
        start:
            entry.start_name === CURRENT_LOCATION_LABEL
                ? null
                : { position: entry.start, label: entry.start_name },
        goal: { position: entry.goal, label: entry.goal_name },
    };
}
