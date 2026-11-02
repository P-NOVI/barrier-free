import { useEffect, useState } from 'react';

import { fetchCongestion, type SensorCongestion } from '../lib/congestionApi';

export type CongestionState =
    | { status: 'idle' }
    | { status: 'loading' }
    | { status: 'success'; sensors: SensorCongestion[] }
    | { status: 'error'; message: string };

type Settled = Extract<CongestionState, { status: 'success' | 'error' }>;

/** 켜면 센서별 유동인구를 받아 온다. 끄면 요청을 취소하고 받은 값을 버린다. */
export function useCongestion(enabled: boolean): CongestionState {
    const [settled, setSettled] = useState<Settled | null>(null);

    useEffect(() => {
        if (!enabled) {
            return;
        }
        const controller = new AbortController();
        fetchCongestion({ signal: controller.signal })
            .then((sensors) => setSettled({ status: 'success', sensors }))
            .catch((error: unknown) => {
                if (controller.signal.aborted) {
                    return;
                }
                const message =
                    error instanceof Error ? error.message : String(error);
                setSettled({ status: 'error', message });
            });
        return () => {
            controller.abort();
            setSettled(null);
        };
    }, [enabled]);

    if (!enabled) {
        return { status: 'idle' };
    }
    return settled ?? { status: 'loading' };
}
