import { useEffect, useRef, useState } from 'react';

import {
    type LngLat,
    loadKakaoMaps,
    toLatLng,
    toLngLat,
} from '../lib/kakaoMap';

const SEOUL_CITY_HALL: LngLat = [126.9779, 37.5663];
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
// 경로 전체가 보이게 맞출 때 지도 가장자리 여백(px). 아래는 경로 패널 높이만큼 더 둔다.
const FIT_PADDING = { top: 48, side: 32, bottom: 240 };

type MapViewProps = {
    center?: LngLat;
    start?: LngLat | null;
    goal?: LngLat | null;
    path?: LngLat[] | null;
    onMapClick?: (position: LngLat) => void;
};

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
            FIT_PADDING.top,
            FIT_PADDING.side,
            FIT_PADDING.bottom,
            FIT_PADDING.side,
        );
        return () => lines.forEach((line) => line.setMap(null));
    }, [map, path, start, goal]);
}

export default function MapView({
    center = SEOUL_CITY_HALL,
    start,
    goal,
    path,
    onMapClick,
}: MapViewProps) {
    const containerRef = useRef<HTMLDivElement>(null);
    const mapRef = useRef<kakao.maps.Map | null>(null);
    const centerRef = useRef(center);
    const onMapClickRef = useRef(onMapClick);
    const [map, setMap] = useState<kakao.maps.Map | null>(null);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        onMapClickRef.current = onMapClick;
    }, [onMapClick]);

    useEffect(() => {
        centerRef.current = center;
        mapRef.current?.setCenter(toLatLng(center));
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
                maps.event.addListener(
                    map,
                    'click',
                    (event: kakao.maps.event.MouseEvent) =>
                        onMapClickRef.current?.(toLngLat(event.latLng)),
                );
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

    useRouteLine(map, path, start, goal);
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
