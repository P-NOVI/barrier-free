import { useCallback, useRef, useState } from 'react';

import MapView, { type FitPadding } from './components/MapView';
import MyLocationControl from './components/MyLocationControl';
import PlaceInfoCard from './components/PlaceInfoCard';
import PlaceSearch from './components/PlaceSearch';
import RoutePanel from './components/RoutePanel';
import { useMediaQuery } from './hooks/useMediaQuery';
import { useRoute } from './hooks/useRoute';
import type { LocationFix } from './lib/geolocation';
import { type LngLat, SEOUL_CITY_HALL } from './lib/kakaoMap';
import { findAddress } from './lib/placeApi';
import { DEFAULT_PRESET, type PresetId } from './lib/presets';
import {
    type Endpoint,
    type EndpointRole,
    MAP_CLICK_LABEL,
    NO_ENDPOINTS,
    type PickedPlace,
    toPickedPlace,
} from './lib/selection';

// 이보다 넓으면 왼쪽 위에 패널 카드 하나, 좁으면 검색창·경로 패널을 위아래에 띄운다.
// index.css 와 같은 값.
const WIDE_LAYOUT = '(min-width: 768px)';
// 경로에 맞출 때 패널에 가리지 않게 둘 여백(px)
const FIT_PADDING: Record<'wide' | 'narrow', FitPadding> = {
    // 왼쪽은 패널 카드(여백 12 + 폭 380)만큼 더 둔다.
    wide: { top: 48, right: 48, bottom: 48, left: 440 },
    // 위는 검색창, 아래는 경로 패널 높이만큼 더 둔다.
    narrow: { top: 160, right: 32, bottom: 240, left: 32 },
};

export default function App() {
    const wide = useMediaQuery(WIDE_LAYOUT);
    const [preset, setPreset] = useState<PresetId>(DEFAULT_PRESET);
    const [endpoints, setEndpoints] = useState(NO_ENDPOINTS);
    // 지도를 눌러 고른 장소. 카드로 이름·주소를 보이고, 출발·도착 버튼을 눌러야 길찾기에 들어간다.
    const [picked, setPicked] = useState<PickedPlace | null>(null);
    // 검색이나 현재 위치로 마지막에 고른 곳. 지도를 그리로 옮긴다.
    const [focus, setFocus] = useState<LngLat | null>(null);
    // 지도 화면 중심. 장소 검색은 이 근처를 앞에 둔다.
    const [mapCenter, setMapCenter] = useState<LngLat>(SEOUL_CITY_HALL);
    // 마지막으로 찾은 내 위치. 지도에 파란 점으로 보인다.
    const [myLocation, setMyLocation] = useState<LocationFix | null>(null);
    const start = endpoints.start?.position ?? null;
    const goal = endpoints.goal?.position ?? null;
    const route = useRoute(start, goal, preset);

    // 마지막으로 누른 곳. 응답을 기다리는 사이 다른 곳을 눌렀는지 구분한다(배열 자체로 비교).
    const latestClick = useRef<LngLat | null>(null);

    const handleMapClick = useCallback((position: LngLat) => {
        // 새로 누르면 이전 카드는 닫고, 이름·주소가 오면 그때 카드를 띄운다.
        latestClick.current = position;
        setPicked(null);
        const show = (found: { name: string; address: string } | null) => {
            if (latestClick.current === position) {
                setPicked(toPickedPlace(position, found));
            }
        };
        findAddress(position)
            .then((address) =>
                show(
                    address && {
                        name: address.name,
                        address: address.road_address || address.address,
                    },
                ),
            )
            // 못 찾아도 카드는 띄워서 "주소를 찾지 못했어요"를 알린다.
            .catch(() => show(null));
    }, []);

    const handleSelect = useCallback(
        (role: EndpointRole, endpoint: Endpoint) => {
            setEndpoints((current) => ({ ...current, [role]: endpoint }));
            // 같은 곳을 다시 골라도 지도가 옮겨 가게 새 배열로 둔다.
            const [lng, lat] = endpoint.position;
            setFocus([lng, lat]);
        },
        [],
    );

    const handlePick = useCallback(
        (role: EndpointRole) => {
            if (!picked) {
                return;
            }
            // 이미 지도에서 보고 있는 곳이라 handleSelect 와 달리 지도를 옮기지 않는다.
            setEndpoints((current) => ({
                ...current,
                [role]: {
                    position: picked.position,
                    label: picked.name ?? MAP_CLICK_LABEL,
                },
            }));
            setPicked(null);
        },
        [picked],
    );

    const showMyLocation = useCallback((fix: LocationFix) => {
        setMyLocation(fix);
        setFocus(fix.position);
    }, []);

    return (
        <div className="app">
            <aside className="side-panel" aria-label="길찾기">
                <header className="side-panel__header">
                    <h1>베리어프리</h1>
                </header>
                <PlaceSearch
                    endpoints={endpoints}
                    near={mapCenter}
                    onSelect={handleSelect}
                    onLocate={setMyLocation}
                />
                <RoutePanel
                    preset={preset}
                    endpoints={endpoints}
                    route={route}
                    onPresetChange={setPreset}
                    onReset={() => setEndpoints(NO_ENDPOINTS)}
                />
            </aside>
            <MapView
                center={focus ?? undefined}
                start={start}
                goal={goal}
                picked={picked?.position}
                popup={
                    picked && (
                        <PlaceInfoCard
                            place={picked}
                            onPick={handlePick}
                            onClose={() => setPicked(null)}
                        />
                    )
                }
                path={
                    route.status === 'success' ? route.route.coordinates : null
                }
                fitPadding={wide ? FIT_PADDING.wide : FIT_PADDING.narrow}
                onMapClick={handleMapClick}
                onCenterChange={setMapCenter}
                myLocation={myLocation}
            />
            <MyLocationControl onLocate={showMyLocation} />
        </div>
    );
}
