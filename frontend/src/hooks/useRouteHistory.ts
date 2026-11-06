import { useEffect, useRef } from 'react';

import { addRoute, toRouteEntry } from '../lib/historyApi';
import type { PresetId } from '../lib/presets';
import type { RouteResponse } from '../lib/routeApi';
import type { Endpoints } from '../lib/selection';
import type { RouteState } from './useRoute';

/**
 * 경로를 찾으면 최근 경로에 남긴다. 기록은 쿠키의 사용자(게스트·회원) 것이다.
 * 안내 중 경로를 벗어나 다시 찾은 경로는 남기지 않는다.
 */
export function useRouteHistory(
    endpoints: Endpoints,
    preset: PresetId,
    route: RouteState,
    navigating: boolean,
): void {
    // 이미 본 경로. 같은 결과를 두 번 남기지 않는다.
    const seen = useRef<RouteResponse | null>(null);

    useEffect(() => {
        if (route.status !== 'success' || route.route === seen.current) {
            return;
        }
        seen.current = route.route;
        const entry = toRouteEntry(endpoints, preset, route.route.distance_m);
        if (navigating || !entry) {
            return;
        }
        // 기록을 못 남겨도 길찾기에는 영향이 없다.
        addRoute(entry).catch(() => undefined);
    }, [endpoints, preset, route, navigating]);
}
