// 즐겨찾기한 경로(내 경로). 쿠키의 사용자(게스트·회원) 것만 오간다.
// 요청·응답 형식은 backend/app/schemas.py 의 SavedRoute* 와 같다.

import { type ApiOptions, requestJson } from './apiClient';
import {
    inOrder,
    type RouteHistory,
    type RouteHistoryRequest,
} from './historyApi';

/** 최근 경로와 같은 칸이다. 최근 경로를 고를 때와 같이 다시 찾을 수 있다. */
export type SavedRouteRequest = RouteHistoryRequest;
export type SavedRoute = RouteHistory;

export async function fetchSavedRoutes(
    options?: ApiOptions,
): Promise<SavedRoute[]> {
    const { routes } = await requestJson<{ routes: SavedRoute[] }>(
        {
            path: '/api/me/saved-routes',
            failureMessage: '내 경로를 불러오지 못했습니다.',
        },
        options,
    );
    return routes;
}

/** 출발·도착 위치와 이동 조건이 같은 경로가 있으면 바꿔 저장한다. */
export function addSavedRoute(
    entry: SavedRouteRequest,
    options?: ApiOptions,
): Promise<SavedRoute> {
    return inOrder(() =>
        requestJson<SavedRoute>(
            {
                path: '/api/me/saved-routes',
                body: entry,
                failureMessage: '경로를 저장하지 못했습니다.',
            },
            options,
        ),
    );
}

export function deleteSavedRoute(
    id: number,
    options?: ApiOptions,
): Promise<void> {
    return inOrder(() =>
        requestJson<void>(
            {
                path: `/api/me/saved-routes/${id}`,
                method: 'DELETE',
                failureMessage: '경로를 지우지 못했습니다.',
            },
            options,
        ),
    );
}

type RouteKey = Pick<RouteHistoryRequest, 'start' | 'goal'> & {
    preset: string;
};

/** 출발·도착 위치와 이동 조건이 같은지. 백엔드 saved_route_repository 와 같은 규칙이다. */
export function isSameRoute(route: RouteKey, other: RouteKey): boolean {
    return (
        route.preset === other.preset &&
        route.start[0] === other.start[0] &&
        route.start[1] === other.start[1] &&
        route.goal[0] === other.goal[0] &&
        route.goal[1] === other.goal[1]
    );
}

/** 지금 경로를 이미 저장했으면 그 경로 */
export function findSavedRoute(
    routes: SavedRoute[],
    entry: RouteKey | null,
): SavedRoute | null {
    return entry
        ? (routes.find((route) => isSameRoute(route, entry)) ?? null)
        : null;
}
