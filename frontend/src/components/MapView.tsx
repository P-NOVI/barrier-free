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

type MapViewProps = {
    center?: LngLat;
    onMapClick?: (position: LngLat) => void;
};

export default function MapView({
    center = SEOUL_CITY_HALL,
    onMapClick,
}: MapViewProps) {
    const containerRef = useRef<HTMLDivElement>(null);
    const mapRef = useRef<kakao.maps.Map | null>(null);
    const centerRef = useRef(center);
    const onMapClickRef = useRef(onMapClick);
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
