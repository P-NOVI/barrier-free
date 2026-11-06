import { useEffect } from 'react';

/** active 인 동안 화면이 꺼지지 않게 한다. 지원하지 않는 브라우저에서는 아무것도 하지 않는다. */
export function useWakeLock(active: boolean) {
    useEffect(() => {
        if (!active || !('wakeLock' in navigator)) {
            return;
        }
        let lock: WakeLockSentinel | null = null;
        let stopped = false;
        const request = () => {
            navigator.wakeLock
                .request('screen')
                .then((granted) => {
                    if (stopped) {
                        void granted.release();
                    } else {
                        lock = granted;
                    }
                })
                // 절전 모드 등으로 거절되면 화면 켜둠 없이 안내를 계속한다.
                .catch(() => undefined);
        };
        // 다른 탭·앱에 다녀오면 브라우저가 풀어 버리므로 다시 요청한다.
        const handleVisibility = () => {
            if (document.visibilityState === 'visible') {
                request();
            }
        };
        request();
        document.addEventListener('visibilitychange', handleVisibility);
        return () => {
            stopped = true;
            document.removeEventListener('visibilitychange', handleVisibility);
            void lock?.release();
        };
    }, [active]);
}
