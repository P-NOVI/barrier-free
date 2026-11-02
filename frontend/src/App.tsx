import { useCallback, useEffect, useRef, useState } from 'react';

import AccountMenu from './components/AccountMenu';
import CongestionToggle from './components/CongestionToggle';
import MapView, { type FitPadding } from './components/MapView';
import MyLocationControl from './components/MyLocationControl';
import NavigationPanel from './components/NavigationPanel';
import PlaceInfoCard from './components/PlaceInfoCard';
import PlaceSearch from './components/PlaceSearch';
import RoutePanel from './components/RoutePanel';
import { useCongestion } from './hooks/useCongestion';
import { useMediaQuery } from './hooks/useMediaQuery';
import { useNavigation } from './hooks/useNavigation';
import { useRoute } from './hooks/useRoute';
import { useRouteHistory } from './hooks/useRouteHistory';
import { useVoiceGuidance } from './hooks/useVoiceGuidance';
import { useWakeLock } from './hooks/useWakeLock';
import { type Elevator, elevatorName, fetchElevators } from './lib/elevators';
import type { LocationFix } from './lib/geolocation';
import { type RouteHistory, routeEndpoints } from './lib/historyApi';
import { type LngLat, SEOUL_CITY_HALL } from './lib/kakaoMap';
import { findAddress } from './lib/placeApi';
import { DEFAULT_PRESET, isPresetId, type PresetId } from './lib/presets';
import {
    CURRENT_LOCATION_LABEL,
    type Endpoint,
    type EndpointRole,
    MAP_CLICK_LABEL,
    NO_ENDPOINTS,
    type PickedPlace,
    toPickedPlace,
} from './lib/selection';
import {
    canSpeak,
    speak,
    START_TEXT,
    stopSpeaking,
    VOICE_ON_TEXT,
} from './lib/voiceGuidance';

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
    const [navigating, setNavigating] = useState(false);
    // 안내 중 지도가 내 위치를 따라가는지. 지도를 끌면 멈추고, 내 위치 버튼을 누르면 다시 따라간다.
    const [following, setFollowing] = useState(true);
    // 음성 안내. 음성 기능이 없는 브라우저에서는 끈다.
    const speechSupported = canSpeak();
    const [voice, setVoice] = useState(speechSupported);
    // 센서별 유동인구를 지도에 보일지. 켤 때 받아 온다.
    const [showCongestion, setShowCongestion] = useState(false);
    const congestion = useCongestion(showCongestion);
    const [elevators, setElevators] = useState<Elevator[]>([]);
    const [elevatorError, setElevatorError] = useState<string | null>(null);
    const [showElevators, setShowElevators] = useState(false);
    const start = endpoints.start?.position ?? null;
    const goal = endpoints.goal?.position ?? null;
    const route = useRoute(start, goal, preset);
    useRouteHistory(endpoints, preset, route, navigating);
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
    useVoiceGuidance(
        navigating && voice,
        navigation,
        route.status === 'loading',
    );
    const navigationFix = navigation.fix;

    // 마지막으로 누른 곳. 응답을 기다리는 사이 다른 곳을 눌렀는지 구분한다(배열 자체로 비교).
    const latestClick = useRef<LngLat | null>(null);

    useEffect(() => {
        let cancelled = false;
        fetchElevators()
            .then((data) => {
                if (!cancelled) {
                    setElevators(data);
                }
            })
            .catch((reason: unknown) => {
                if (!cancelled) {
                    setElevatorError(
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

    // name 을 주면 찾은 이름 대신 그 이름을 쓴다(엘리베이터). 주소는 position 으로 찾는다.
    const pickPlace = useCallback((position: LngLat, name?: string) => {
        // 새로 누르면 이전 카드는 닫고, 이름·주소가 오면 그때 카드를 띄운다.
        latestClick.current = position;
        setPicked(null);
        const show = (found: { name: string; address: string } | null) => {
            if (latestClick.current === position) {
                setPicked(
                    toPickedPlace(
                        position,
                        name ? { name, address: found?.address ?? '' } : found,
                    ),
                );
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

    const handleMapClick = useCallback(
        (position: LngLat) => pickPlace(position),
        [pickPlace],
    );

    const handleElevatorClick = useCallback(
        (elevator: Elevator) =>
            pickPlace(elevator.position, elevatorName(elevator)),
        [pickPlace],
    );

    const handleSelect = useCallback(
        (role: EndpointRole, endpoint: Endpoint) => {
            setEndpoints((current) => ({ ...current, [role]: endpoint }));
            // 같은 곳을 다시 골라도 지도가 옮겨 가게 새 배열로 둔다.
            const [lng, lat] = endpoint.position;
            setFocus([lng, lat]);
        },
        [],
    );

    // 최근 경로: 그때의 출발·도착과 프리셋으로 다시 찾는다.
    const handleSelectRoute = useCallback(
        (entry: RouteHistory) => {
            const { start: from, goal: to } = routeEndpoints(entry);
            if (from) {
                handleSelect('start', from);
            }
            handleSelect('goal', to);
            if (isPresetId(entry.preset)) {
                setPreset(entry.preset);
            }
        },
        [handleSelect],
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
        setFollowing(true);
    }, []);

    // 휴대폰 브라우저는 버튼을 누를 때 처음 소리를 내야 이후 안내도 읽어 준다.
    const startNavigation = useCallback(() => {
        setFollowing(true);
        setNavigating(true);
        if (voice) {
            speak(START_TEXT);
        }
    }, [voice]);

    const stopNavigation = () => {
        // 안내를 마친 자리를 내 위치로 남긴다.
        if (navigationFix) {
            setMyLocation(navigationFix);
        }
        setNavigating(false);
        stopSpeaking();
    };

    const changeVoice = (on: boolean) => {
        setVoice(on);
        if (on) {
            speak(VOICE_ON_TEXT);
        } else {
            stopSpeaking();
        }
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
                    onSelectRoute={handleSelectRoute}
                    onLocate={setMyLocation}
                />
                {navigating ? (
                    <NavigationPanel
                        route={route}
                        navigation={navigation}
                        following={following}
                        voice={voice}
                        onVoiceChange={
                            speechSupported ? changeVoice : undefined
                        }
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
                path={shownRoute?.coordinates ?? null}
                elevators={showElevators ? elevators : undefined}
                fitPadding={wide ? FIT_PADDING.wide : FIT_PADDING.narrow}
                fitRoute={!navigating}
                follow={
                    navigating && following
                        ? (navigationFix?.position ?? null)
                        : null
                }
                // 안내 중에는 지도를 눌러도 출발·도착을 바꾸지 않는다.
                onMapClick={navigating ? undefined : handleMapClick}
                onElevatorClick={navigating ? undefined : handleElevatorClick}
                onCenterChange={setMapCenter}
                onDragStart={stopFollowing}
                myLocation={navigationFix ?? myLocation}
                congestion={
                    congestion.status === 'success' ? congestion.sensors : null
                }
            />
            <CongestionToggle
                enabled={showCongestion}
                state={congestion}
                onChange={setShowCongestion}
            />
            {!navigating && <AccountMenu />}
            <MyLocationControl
                onLocate={showMyLocation}
                locate={
                    navigationFix
                        ? () => Promise.resolve(navigationFix)
                        : undefined
                }
            />
            <button
                type="button"
                className="map-toggle"
                aria-pressed={showElevators}
                onClick={() => setShowElevators((shown) => !shown)}
            >
                엘리베이터
            </button>
            {elevatorError && (
                <p role="alert" className="map-view__error">
                    {elevatorError}
                </p>
            )}
        </div>
    );
}
