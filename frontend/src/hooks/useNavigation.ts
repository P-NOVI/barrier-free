import { useEffect, useEffectEvent, useMemo, useRef, useState } from 'react';

import { type LocationFix, watchLocation } from '../lib/geolocation';
import type { LngLat } from '../lib/kakaoMap';
import {
    type GoalGap,
    judge,
    type Judgement,
    lineLengthM,
    NEW_TRACKER,
    onGoalGap,
    progressAlong,
    type RouteProgress,
    trackOffRoute,
    withGoalGap,
} from '../lib/navigation';
import type { RouteOption } from '../lib/routeApi';
import { type NextTurn, nextTurn, routeTurns } from '../lib/turns';

export type NavigationState = {
    /** 마지막으로 받은 내 위치 */
    fix: LocationFix | null;
    /** 진행 정도. 남은 거리는 도착 점선까지 센다. */
    progress: RouteProgress | null;
    judgement: Judgement | null;
    /** 다음 회전(없으면 도착)과 거기까지 거리 */
    next: NextTurn | null;
    /** 점선 구간을 걷는 중이면 그 종류. 아니면 null */
    goalGap: GoalGap | null;
    /** 위치를 받지 못한 이유. 다음 위치가 오면 지운다. */
    error: string | null;
};

/**
 * active 인 동안 내 위치를 계속 받아 route 위 진행을 계산한다.
 * goal(찍은 도착지)이 있으면 길 위 경로 끝에서 도착지까지 점선 구간까지 따라간다.
 * 경로를 벗어나면 onReroute 로 지금 위치를 알린다. 경로를 다시 찾는 동안(rerouting)은 판단하지 않는다.
 */
export function useNavigation(
    active: boolean,
    route: RouteOption | null,
    rerouting: boolean,
    onReroute: (position: LngLat) => void,
    goal: LngLat | null = null,
): NavigationState {
    const [fix, setFix] = useState<LocationFix | null>(null);
    const [error, setError] = useState<string | null>(null);
    const tracker = useRef(NEW_TRACKER);
    const line = useMemo(
        () =>
            route && goal
                ? withGoalGap(route, [
                      ...(route.goal_entrance ? [route.goal_entrance] : []),
                      goal,
                  ])
                : route,
        [route, goal],
    );

    const handleFix = useEffectEvent((next: LocationFix) => {
        setFix(next);
        setError(null);
        if (!line || rerouting) {
            return;
        }
        const judgement = judge(
            progressAlong(line, next.position),
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

    const turns = useMemo(() => (route ? routeTurns(route) : []), [route]);
    const progress = useMemo(
        () => (fix && line ? progressAlong(line, fix.position) : null),
        [fix, line],
    );
    const next = useMemo(
        () => (progress ? nextTurn(turns, progress) : null),
        [turns, progress],
    );
    const judgement = fix && progress ? judge(progress, fix.accuracy) : null;
    const goalGapM = route && line ? lineLengthM(line) - lineLengthM(route) : 0;
    return {
        fix,
        progress,
        judgement,
        next,
        goalGap:
            route &&
            progress &&
            judgement === 'on_route' &&
            onGoalGap(progress, goalGapM)
                ? route.goal_entrance
                    ? 'entrance'
                    : 'gap'
                : null,
        error,
    };
}
