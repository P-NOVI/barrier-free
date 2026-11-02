import { useCallback, useEffect, useState } from 'react';

import {
    deleteRoute,
    deleteSearch,
    fetchRoutes,
    fetchSearches,
    type RouteHistory,
    type SearchHistory,
} from '../lib/historyApi';

export type RecentHistory = {
    searches: SearchHistory[];
    routes: RouteHistory[];
    removeSearch: (id: number) => void;
    removeRoute: (id: number) => void;
};

type Lists = Pick<RecentHistory, 'searches' | 'routes'>;

const EMPTY: Lists = { searches: [], routes: [] };

/** active 가 될 때마다 최근 검색·경로를 새로 받는다. 못 받으면 빈 목록이다. */
export function useRecentHistory(active: boolean): RecentHistory {
    const [lists, setLists] = useState<Lists>(EMPTY);

    useEffect(() => {
        if (!active) {
            return;
        }
        const controller = new AbortController();
        const options = { signal: controller.signal };
        Promise.all([fetchSearches(options), fetchRoutes(options)])
            .then(([searches, routes]) => setLists({ searches, routes }))
            // 백엔드(DB)가 없으면 목록 없이 검색만 쓴다.
            .catch(() => undefined);
        return () => controller.abort();
    }, [active]);

    // 지운 것은 바로 감춘다. 지우지 못했으면 다음에 받을 때 다시 보인다.
    const removeSearch = useCallback((id: number) => {
        setLists((current) => ({
            ...current,
            searches: current.searches.filter((entry) => entry.id !== id),
        }));
        deleteSearch(id).catch(() => undefined);
    }, []);

    const removeRoute = useCallback((id: number) => {
        setLists((current) => ({
            ...current,
            routes: current.routes.filter((entry) => entry.id !== id),
        }));
        deleteRoute(id).catch(() => undefined);
    }, []);

    return { ...lists, removeSearch, removeRoute };
}
