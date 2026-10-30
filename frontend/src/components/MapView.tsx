import { useEffect, useMemo, useRef, useState } from 'react';

import {
    type LngLat,
    loadKakaoMaps,
    SEOUL_CITY_HALL,
    toLatLng,
    toLngLat,
} from '../lib/kakaoMap';

// 카카오맵 확대 수준. 숫자가 작을수록 확대 (1~14)
const DEFAULT_LEVEL = 4;

const ROUTE_LINE: Omit<kakao.maps.PolylineOptions, 'path'> = {
    strokeWeight: 6,
    strokeColor: '#1a73e8',
    strokeOpacity: 0.9,
    strokeStyle: 'solid',
};
// 찍은 위치와 실제 경로 시작·끝 지점 사이를 잇는 점선
const GAP_LINE: Omit<kakao.maps.PolylineOptions, 'path'> = {
    strokeWeight: 3,
    strokeColor: '#5f6368',
    strokeOpacity: 0.8,
    strokeStyle: 'shortdash',
};
/** 경로 전체가 보이게 맞출 때 지도 가장자리 여백(px) */
export type FitPadding = {
    top: number;
    right: number;
    bottom: number;
    left: number;
};

const DEFAULT_FIT_PADDING: FitPadding = {
    top: 48,
    right: 48,
    bottom: 48,
    left: 48,
};

type MapViewProps = {
    center?: LngLat;
    start?: LngLat | null;
    goal?: LngLat | null;
    path?: LngLat[] | null;
    /** 지도 위에 패널이 떠 있으면 그만큼 여백을 더 준다. 바뀌면 경로에 다시 맞춘다. */
    fitPadding?: FitPadding;
    onMapClick?: (position: LngLat) => void;
    /** 지도 이동·확대가 끝날 때마다 화면 중심을 알린다. */
    onCenterChange?: (center: LngLat) => void;
};

/** 지도 이벤트를 붙이고, 지도나 handler 가 바뀌면 뗀다. */
function useMapEvent(
    map: kakao.maps.Map | null,
    type: 'click' | 'idle',
    handler:
        | ((event: kakao.maps.event.MouseEvent) => void)
        | (() => void)
        | undefined,
) {
    useEffect(() => {
        if (!map || !handler) {
            return;
        }
        kakao.maps.event.addListener(map, type, handler);
        return () => kakao.maps.event.removeListener(map, type, handler);
    }, [map, type, handler]);
}

function usePin(
    map: kakao.maps.Map | null,
    position: LngLat | null | undefined,
    label: string,
    modifier: string,
) {
    useEffect(() => {
        if (!map || !position) {
            return;
        }
        const content = document.createElement('div');
        content.className = `map-pin map-pin--${modifier}`;
        content.textContent = label;
        const overlay = new kakao.maps.CustomOverlay({
            position: toLatLng(position),
            content,
            yAnchor: 1,
        });
        overlay.setMap(map);
        return () => overlay.setMap(null);
    }, [map, position, label, modifier]);
}

function useRouteLine(
    map: kakao.maps.Map | null,
    path: LngLat[] | null | undefined,
    start: LngLat | null | undefined,
    goal: LngLat | null | undefined,
    padding: FitPadding,
) {
    useEffect(() => {
        if (!map || !path || path.length < 2) {
            return;
        }
        const gaps = [
            start && [start, path[0]],
            goal && [path[path.length - 1], goal],
        ].filter((gap): gap is LngLat[] => Boolean(gap));
        const lines = [
            new kakao.maps.Polyline({
                ...ROUTE_LINE,
                path: path.map(toLatLng),
            }),
            ...gaps.map(
                (gap) =>
                    new kakao.maps.Polyline({
                        ...GAP_LINE,
                        path: gap.map(toLatLng),
                    }),
            ),
        ];
        lines.forEach((line) => line.setMap(map));

        const bounds = new kakao.maps.LatLngBounds();
        [...path, ...gaps.flat()].forEach((point) =>
            bounds.extend(toLatLng(point)),
        );
        map.setBounds(
            bounds,
            padding.top,
            padding.right,
            padding.bottom,
            padding.left,
        );
        return () => lines.forEach((line) => line.setMap(null));
    }, [map, path, start, goal, padding]);
}

export default function MapView({
    center = SEOUL_CITY_HALL,
    start,
    goal,
    path,
    fitPadding = DEFAULT_FIT_PADDING,
    onMapClick,
    onCenterChange,
}: MapViewProps) {
    const containerRef = useRef<HTMLDivElement>(null);
    const mapRef = useRef<kakao.maps.Map | null>(null);
    const centerRef = useRef(center);
    const [map, setMap] = useState<kakao.maps.Map | null>(null);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        centerRef.current = center;
        // 화면보다 먼 곳이면 카카오맵이 애니메이션 없이 옮긴다.
        mapRef.current?.panTo(toLatLng(center));
    }, [center]);

    useEffect(() => {
        let cancelled = false;
        loadKakaoMaps()
            .then((maps) => {
                if (cancelled || !containerRef.current || mapRef.current) {
                    return;
                }
                const map = new maps.Map(containerRef.current, {
                    center: toLatLng(centerRef.current),
                    level: DEFAULT_LEVEL,
                });
                mapRef.current = map;
                setMap(map);
            })
            .catch((reason: unknown) => {
                if (!cancelled) {
                    setError(
                        reason instanceof Error
                            ? reason.message
                            : String(reason),
                    );
                }
            });
        return () => {
            cancelled = true;
        };
    }, []);

    const handleClick = useMemo(
        () =>
            onMapClick &&
            ((event: kakao.maps.event.MouseEvent) =>
                onMapClick(toLngLat(event.latLng))),
        [onMapClick],
    );
    const handleIdle = useMemo(() => {
        if (!map || !onCenterChange) {
            return undefined;
        }
        return () => onCenterChange(toLngLat(map.getCenter()));
    }, [map, onCenterChange]);

    useMapEvent(map, 'click', handleClick);
    useMapEvent(map, 'idle', handleIdle);
    useEffect(() => {
        const container = containerRef.current;
        if (!map || !container) {
            return;
        }
        // 화면 배치가 바뀌어 지도 크기가 달라지면 카카오맵에 알려야 지도가 빈칸 없이 그려진다.
        const observer = new ResizeObserver(() => map.relayout());
        observer.observe(container);
        return () => observer.disconnect();
    }, [map]);

    useRouteLine(map, path, start, goal, fitPadding);
    usePin(map, start, '출발', 'start');
    usePin(map, goal, '도착', 'goal');

    return (
        <div className="map-view">
            <div ref={containerRef} className="map-view__canvas" />
            <a
                className="map-view__attribution"
                href="https://www.openstreetmap.org/copyright"
                target="_blank"
                rel="noreferrer"
            >
                © OpenStreetMap contributors
            </a>
            {error && (
                <p role="alert" className="map-view__error">
                    {error}
                </p>
            )}
        </div>
    );
}
