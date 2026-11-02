import { useEffect, useState } from 'react';

import type { LngLat } from '../lib/kakaoMap';
import type { PresetId } from '../lib/presets';
import { fetchRoute, type RouteResponse } from '../lib/routeApi';

export type RouteState =
    | { status: 'idle' }
    | { status: 'loading' }
    | { status: 'success'; route: RouteResponse }
    | { status: 'error'; message: string };

type Settled = Extract<RouteState, { status: 'success' | 'error' }>;

/** 출발·도착·프리셋이 바뀔 때마다 경로를 다시 요청한다. 이전 요청은 취소한다. */
export function useRoute(
    start: LngLat | null,
    goal: LngLat | null,
    preset: PresetId,
): RouteState {
    // 어느 요청의 결과인지 key 로 구분해서, 입력이 바뀌면 결과가 올 때까지 loading 으로 본다.
    const key = start && goal ? JSON.stringify([start, goal, preset]) : null;
    const [settled, setSettled] = useState<{
        key: string;
        state: Settled;
    } | null>(null);

    useEffect(() => {
        if (!key || !start || !goal) {
            return;
        }
        const controller = new AbortController();
        fetchRoute({ start, goal, preset }, { signal: controller.signal })
            .then((route) =>
                setSettled({ key, state: { status: 'success', route } }),
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
    }, [key, start, goal, preset]);

    if (!key) {
        return { status: 'idle' };
    }
    if (settled?.key !== key) {
        return { status: 'loading' };
    }
    return settled.state;
}
