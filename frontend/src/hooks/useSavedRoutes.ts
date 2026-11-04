import { useCallback, useEffect, useState } from 'react';

import {
    addSavedRoute,
    deleteSavedRoute,
    fetchSavedRoutes,
    isSameRoute,
    type SavedRoute,
    type SavedRouteRequest,
} from '../lib/savedRoutesApi';

export type SavedRoutes = {
    routes: SavedRoute[];
    /** 처음 불러오기에 실패하면(백엔드·DB가 꺼짐) false. 저장 버튼을 숨긴다. */
    available: boolean;
    error: string | null;
    add: (entry: SavedRouteRequest) => void;
    remove: (id: number) => void;
    /** 로그인·로그아웃으로 사용자가 바뀌면 다시 불러온다. */
    reload: () => void;
};

function messageOf(reason: unknown): string {
    return reason instanceof Error ? reason.message : String(reason);
}

/** 즐겨찾기한 경로(내 경로) */
export function useSavedRoutes(): SavedRoutes {
    const [routes, setRoutes] = useState<SavedRoute[]>([]);
    const [available, setAvailable] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [version, setVersion] = useState(0);

    useEffect(() => {
        let cancelled = false;
        fetchSavedRoutes()
            .then((found) => {
                if (!cancelled) {
                    setRoutes(found);
                    setAvailable(true);
                }
            })
            .catch(() => {
                if (!cancelled) {
                    setRoutes([]);
                    setAvailable(false);
                }
            });
        return () => {
            cancelled = true;
        };
    }, [version]);

    const add = useCallback((entry: SavedRouteRequest) => {
        setError(null);
        addSavedRoute(entry)
            .then((saved) =>
                setRoutes((current) => [
                    saved,
                    ...current.filter((route) => !isSameRoute(route, saved)),
                ]),
            )
            .catch((reason: unknown) => setError(messageOf(reason)));
    }, []);

    const remove = useCallback((id: number) => {
        setError(null);
        deleteSavedRoute(id)
            .then(() =>
                setRoutes((current) =>
                    current.filter((route) => route.id !== id),
                ),
            )
            .catch((reason: unknown) => setError(messageOf(reason)));
    }, []);

    const reload = useCallback(() => setVersion((current) => current + 1), []);

    return { routes, available, error, add, remove, reload };
}
