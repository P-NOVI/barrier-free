import { useState } from 'react';

import { getCurrentPosition, type LocationFix } from '../lib/geolocation';

type MyLocationControlProps = {
    onLocate: (fix: LocationFix) => void;
};

type LocateState =
    | { status: 'idle' }
    | { status: 'locating' }
    | { status: 'error'; message: string };

/** 지도 위 '내 위치' 버튼. 찾으면 알리고, 못 찾으면 이유를 버튼 옆에 띄운다. */
export default function MyLocationControl({
    onLocate,
}: MyLocationControlProps) {
    const [locate, setLocate] = useState<LocateState>({ status: 'idle' });
    const locating = locate.status === 'locating';

    const handleClick = () => {
        setLocate({ status: 'locating' });
        getCurrentPosition()
            .then((fix) => {
                setLocate({ status: 'idle' });
                onLocate(fix);
            })
            .catch((error: unknown) =>
                setLocate({
                    status: 'error',
                    message:
                        error instanceof Error ? error.message : String(error),
                }),
            );
    };

    return (
        <div className="my-location-control">
            {locate.status === 'error' && (
                <p role="alert" className="my-location-control__error">
                    {locate.message}
                </p>
            )}
            <button
                type="button"
                className="my-location-control__button"
                aria-label={locating ? '내 위치 찾는 중' : '내 위치 보기'}
                title="내 위치 보기"
                disabled={locating}
                onClick={handleClick}
            >
                <svg viewBox="0 0 24 24" aria-hidden="true">
                    <circle
                        cx="12"
                        cy="12"
                        r="7"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2"
                    />
                    <circle cx="12" cy="12" r="3" fill="currentColor" />
                    <path
                        d="M12 2v3M12 19v3M2 12h3M19 12h3"
                        stroke="currentColor"
                        strokeWidth="2"
                        strokeLinecap="round"
                    />
                </svg>
            </button>
        </div>
    );
}
