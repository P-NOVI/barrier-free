import { useCallback, useSyncExternalStore } from 'react';

/** CSS 미디어 쿼리가 맞는지. 화면 크기가 바뀌면 다시 그린다. */
export function useMediaQuery(query: string): boolean {
    const subscribe = useCallback(
        (onChange: () => void) => {
            const list = window.matchMedia(query);
            list.addEventListener('change', onChange);
            return () => list.removeEventListener('change', onChange);
        },
        [query],
    );
    return useSyncExternalStore(
        subscribe,
        () => window.matchMedia(query).matches,
    );
}
