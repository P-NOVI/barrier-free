import { useEffect, useState } from 'react';

import type { LngLat } from '../lib/kakaoMap';
import { type Place, searchPlaces } from '../lib/placeApi';

export type PlaceSearchState =
    | { status: 'idle' }
    | { status: 'loading' }
    | { status: 'success'; places: Place[] }
    | { status: 'error'; message: string };

type Settled = Extract<PlaceSearchState, { status: 'success' | 'error' }>;

/** 검색어가 바뀔 때마다 장소를 다시 찾는다. 빈 검색어면 찾지 않고, 이전 요청은 취소한다. */
export function usePlaceSearch(
    query: string,
    near: LngLat | null,
): PlaceSearchState {
    const trimmed = query.trim();
    // useRoute 와 같이, 어느 검색의 결과인지 key 로 구분한다.
    const key = trimmed ? JSON.stringify([trimmed, near]) : null;
    const [settled, setSettled] = useState<{
        key: string;
        state: Settled;
    } | null>(null);

    useEffect(() => {
        if (!key) {
            return;
        }
        const controller = new AbortController();
        searchPlaces(trimmed, near, { signal: controller.signal })
            .then((places) =>
                setSettled({ key, state: { status: 'success', places } }),
            )
            .catch((error: unknown) => {
                if (controller.signal.aborted) {
                    return;
                }
                const message =
                    error instanceof Error ? error.message : String(error);
                setSettled({ key, state: { status: 'error', message } });
            });
        return () => controller.abort();
    }, [key, trimmed, near]);

    if (!key) {
        return { status: 'idle' };
    }
    if (settled?.key !== key) {
        return { status: 'loading' };
    }
    return settled.state;
}
