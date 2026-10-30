import { useCallback, useState } from 'react';

import MapView, { type FitPadding } from './components/MapView';
import MyLocationControl from './components/MyLocationControl';
import NavigationPanel from './components/NavigationPanel';
import PlaceSearch from './components/PlaceSearch';
import RoutePanel from './components/RoutePanel';
import { useMediaQuery } from './hooks/useMediaQuery';
import { useNavigation } from './hooks/useNavigation';
import { useRoute } from './hooks/useRoute';
import { useWakeLock } from './hooks/useWakeLock';
import type { LocationFix } from './lib/geolocation';
import { type LngLat, SEOUL_CITY_HALL } from './lib/kakaoMap';
import { findAddress } from './lib/placeApi';
import { DEFAULT_PRESET, type PresetId } from './lib/presets';
import {
    CURRENT_LOCATION_LABEL,
    type Endpoint,
    type EndpointRole,
    NO_ENDPOINTS,
    renameEndpoint,
    selectEndpoint,
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
    // 검색이나 현재 위치로 마지막에 고른 곳. 지도를 그리로 옮긴다.
    const [focus, setFocus] = useState<LngLat | null>(null);
    // 지도 화면 중심. 장소 검색은 이 근처를 앞에 둔다.
    const [mapCenter, setMapCenter] = useState<LngLat>(SEOUL_CITY_HALL);
    // 마지막으로 찾은 내 위치. 지도에 파란 점으로 보인다.
    const [myLocation, setMyLocation] = useState<LocationFix | null>(null);
    const [navigating, setNavigating] = useState(false);
    // 안내 중 지도가 내 위치를 따라가는지. 지도를 끌면 멈추고, 내 위치 버튼을 누르면 다시 따라간다.
    const [following, setFollowing] = useState(true);
    const start = endpoints.start?.position ?? null;
    const goal = endpoints.goal?.position ?? null;
    const route = useRoute(start, goal, preset);
    // 안내 중 경로를 다시 찾는 동안에는 전 경로를 그대로 보여 준다.
    const shownRoute =
        route.status === 'success'
            ? route.route
            : navigating && route.status === 'loading'
              ? route.previous
              : null;

    // 경로를 벗어나면 지금 위치를 출발지로 경로를 다시 찾는다.
    const reroute = useCallback((position: LngLat) => {
        setEndpoints((current) => ({
            ...current,
            start: { position, label: CURRENT_LOCATION_LABEL },
        }));
    }, []);
    const navigation = useNavigation(
        navigating,
        shownRoute,
        route.status === 'loading',
        reroute,
    );
    useWakeLock(navigating);
    const navigationFix = navigation.fix;

    const handleMapClick = useCallback((position: LngLat) => {
        setEndpoints((current) => selectEndpoint(current, position));
        findAddress(position)
            .then((address) => {
                if (address) {
                    setEndpoints((current) =>
                        renameEndpoint(current, position, address.name),
                    );
                }
            })
            // 이름을 못 찾으면 "지도에서 고른 위치" 그대로 둔다.
            .catch(() => undefined);
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

    const showMyLocation = useCallback((fix: LocationFix) => {
        setMyLocation(fix);
        setFocus(fix.position);
        setFollowing(true);
    }, []);

    const startNavigation = useCallback(() => {
        setFollowing(true);
        setNavigating(true);
    }, []);

    const stopNavigation = () => {
        // 안내를 마친 자리를 내 위치로 남긴다.
        if (navigationFix) {
            setMyLocation(navigationFix);
        }
        setNavigating(false);
    };

    const stopFollowing = useCallback(() => setFollowing(false), []);

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
                {navigating ? (
                    <NavigationPanel
                        route={route}
                        navigation={navigation}
                        following={following}
                        onStop={stopNavigation}
                    />
                ) : (
                    <RoutePanel
                        preset={preset}
                        endpoints={endpoints}
                        route={route}
                        onPresetChange={setPreset}
                        onReset={() => setEndpoints(NO_ENDPOINTS)}
                        onStartNavigation={startNavigation}
                    />
                )}
            </aside>
            <MapView
                center={focus ?? undefined}
                start={start}
                goal={goal}
                path={shownRoute?.coordinates ?? null}
                fitPadding={wide ? FIT_PADDING.wide : FIT_PADDING.narrow}
                fitRoute={!navigating}
                follow={
                    navigating && following
                        ? (navigationFix?.position ?? null)
                        : null
                }
                // 안내 중에는 지도를 눌러도 출발·도착을 바꾸지 않는다.
                onMapClick={navigating ? undefined : handleMapClick}
                onCenterChange={setMapCenter}
                onDragStart={stopFollowing}
                myLocation={navigationFix ?? myLocation}
            />
            <MyLocationControl
                onLocate={showMyLocation}
                locate={
                    navigationFix
                        ? () => Promise.resolve(navigationFix)
                        : undefined
                }
            />
        </div>
    );
}
