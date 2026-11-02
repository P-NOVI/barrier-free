import { useEffect, useRef } from 'react';

import { announcement, REROUTE_TEXT, speak } from '../lib/voiceGuidance';
import type { NavigationState } from './useNavigation';

/** enabled 인 동안 다음 회전, 도착, 경로 다시 찾기를 소리로 알린다. */
export function useVoiceGuidance(
    enabled: boolean,
    { next, judgement }: NavigationState,
    rerouting: boolean,
) {
    // 이미 읽은 안내. 켤 때마다 새로 센다.
    const announced = useRef(new Set<string>());

    useEffect(() => {
        if (enabled) {
            announced.current = new Set();
        }
    }, [enabled]);

    useEffect(() => {
        // 경로를 벗어났거나 위치가 부정확하면 회전 안내가 틀릴 수 있어 읽지 않는다.
        if (
            !enabled ||
            !next ||
            (judgement !== 'on_route' && judgement !== 'arrived')
        ) {
            return;
        }
        const result = announcement(
            next,
            judgement === 'arrived',
            announced.current,
        );
        if (result) {
            result.keys.forEach((key) => announced.current.add(key));
            speak(result.text);
        }
    }, [enabled, next, judgement]);

    useEffect(() => {
        if (enabled && rerouting) {
            speak(REROUTE_TEXT);
        }
    }, [enabled, rerouting]);
}
