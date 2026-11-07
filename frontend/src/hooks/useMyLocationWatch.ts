import { useEffect, useEffectEvent } from 'react';

import {
    type LocationError,
    type LocationFix,
    watchLocation,
} from '../lib/geolocation';

/**
 * active 인 동안 내 위치를 계속 받아 onFix 로 알린다. active 가 꺼지면 멈춘다.
 * 위치를 받지 못하면 onError 로 알린다.
 */
export function useMyLocationWatch(
    active: boolean,
    onFix: (fix: LocationFix) => void,
    onError: (error: LocationError) => void,
) {
    const handleFix = useEffectEvent(onFix);
    const handleError = useEffectEvent(onError);

    useEffect(() => {
        if (!active) {
            return;
        }
        return watchLocation(
            (fix) => handleFix(fix),
            (error) => handleError(error),
        );
    }, [active]);
}
