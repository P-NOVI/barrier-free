import { useEffect, useEffectEvent, useMemo, useRef, useState } from 'react';

import { type LocationFix, watchLocation } from '../lib/geolocation';
import type { LngLat } from '../lib/kakaoMap';
import {
    judge,
    type Judgement,
    NEW_TRACKER,
    progressAlong,
    type RouteLine,
    type RouteProgress,
    trackOffRoute,
} from '../lib/navigation';
import { findTurns, type NextTurn, nextTurn } from '../lib/turns';

export type NavigationState = {
    /** 마지막으로 받은 내 위치 */
    fix: LocationFix | null;
    progress: RouteProgress | null;
    judgement: Judgement | null;
    /** 다음 회전(없으면 도착)과 거기까지 거리 */
    next: NextTurn | null;
    /** 위치를 받지 못한 이유. 다음 위치가 오면 지운다. */
    error: string | null;
};

/**
 * active 인 동안 내 위치를 계속 받아 route 위 진행을 계산한다.
 * 경로를 벗어나면 onReroute 로 지금 위치를 알린다. 경로를 다시 찾는 동안(rerouting)은 판단하지 않는다.
 */
export function useNavigation(
    active: boolean,
    route: RouteLine | null,
    rerouting: boolean,
    onReroute: (position: LngLat) => void,
): NavigationState {
    const [fix, setFix] = useState<LocationFix | null>(null);
    const [error, setError] = useState<string | null>(null);
    const tracker = useRef(NEW_TRACKER);

    const handleFix = useEffectEvent((next: LocationFix) => {
        setFix(next);
        setError(null);
        if (!route || rerouting) {
            return;
        }
        const judgement = judge(
            progressAlong(route, next.position),
            next.accuracy,
        );
        const result = trackOffRoute(tracker.current, judgement, next.position);
        tracker.current = result.tracker;
        if (result.reroute) {
            onReroute(next.position);
        }
    });
    const handleError = useEffectEvent((reason: Error) =>
        setError(reason.message),
    );

    useEffect(() => {
        if (!active) {
            return;
        }
        tracker.current = NEW_TRACKER;
        const stop = watchLocation(
            (next) => handleFix(next),
            (reason) => handleError(reason),
        );
        return () => {
            stop();
            // 다음 안내를 시작할 때 지난 위치를 보이지 않게 한다.
            setFix(null);
            setError(null);
        };
    }, [active]);

    const turns = useMemo(() => (route ? findTurns(route) : []), [route]);
    const progress = useMemo(
        () => (fix && route ? progressAlong(route, fix.position) : null),
        [fix, route],
    );
    const next = useMemo(
        () => (progress ? nextTurn(turns, progress) : null),
        [turns, progress],
    );
    return {
        fix,
        progress,
        judgement: fix && progress ? judge(progress, fix.accuracy) : null,
        next,
        error,
    };
}
