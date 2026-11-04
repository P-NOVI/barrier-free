import {
    type ReactNode,
    useCallback,
    useEffect,
    useMemo,
    useRef,
    useState,
} from 'react';

import AccountMenu from './components/AccountMenu';
import AccountPanel from './components/AccountPanel';
import BottomSheet from './components/BottomSheet';
import MapView, { type FitPadding } from './components/MapView';
import MenuBar from './components/MenuBar';
import MyLocationControl from './components/MyLocationControl';
import NavigationPanel from './components/NavigationPanel';
import PlaceInfoCard from './components/PlaceInfoCard';
import PlaceSearch from './components/PlaceSearch';
import RoutePanel from './components/RoutePanel';
import SavedPanel from './components/SavedPanel';
import TopSearch from './components/TopSearch';
import { useMediaQuery } from './hooks/useMediaQuery';
import { useNavigation } from './hooks/useNavigation';
import { useRoute } from './hooks/useRoute';
import { useRouteHistory } from './hooks/useRouteHistory';
import { useSavedPlaces } from './hooks/useSavedPlaces';
import { useVoiceGuidance } from './hooks/useVoiceGuidance';
import { useWakeLock } from './hooks/useWakeLock';
import { takeLoginFailure } from './lib/authApi';
import { type Elevator, fetchElevators } from './lib/elevators';
import type { LocationFix } from './lib/geolocation';
import { type RouteHistory, routeEndpoints } from './lib/historyApi';
import { type LngLat, SEOUL_CITY_HALL } from './lib/kakaoMap';
import { findAddress } from './lib/placeApi';
import { DEFAULT_PRESET, isPresetId, type PresetId } from './lib/presets';
import {
    placesAt,
    type SavedPlace,
    toSavedPlaceRequest,
} from './lib/savedPlacesApi';
import {
    CURRENT_LOCATION_LABEL,
    type Endpoint,
    type EndpointRole,
    MAP_CLICK_LABEL,
    NO_ENDPOINTS,
    type PickedPlace,
    toPickedPlace,
} from './lib/selection';
import { selectTab, type SheetSnap, type Tab } from './lib/sheet';
import {
    elevatorExitsText,
    elevatorStopText,
    stationElevators,
    toElevatorEndpoints,
} from './lib/stationElevators';
import {
    canSpeak,
    speak,
    START_TEXT,
    stopSpeaking,
    VOICE_ON_TEXT,
} from './lib/voiceGuidance';

// 이보다 넓으면 메뉴·검색을 왼쪽 위에 띄운 패널(위에 메뉴) 하나에 둔다.
// 좁으면 위에 검색창, 아래에 메뉴와 오르내리는 시트를 둔다. index.css 와 같은 값.
const WIDE_LAYOUT = '(min-width: 768px)';
// 경로에 맞출 때 지도 위 검색창·버튼에 가리지 않게 둘 여백(px)
const FIT_PADDING: Record<'wide' | 'narrow', FitPadding> = {
    // 왼쪽은 패널(여백 12 + 폭 380)만큼 더 둔다.
    wide: { top: 48, right: 48, bottom: 48, left: 440 },
    // 위는 검색창 높이. 지도가 메뉴·시트 위에서 끝나므로 아래 여백을 더 두지 않는다.
    narrow: { top: 80, right: 32, bottom: 32, left: 32 },
};
const SHEET_TITLES: Record<Exclude<Tab, 'search'>, string> = {
    route: '길찾기',
    saved: '저장',
    my: 'My',
};
const LOGIN_FAILED_MESSAGE = '로그인하지 못했어요. 다시 시도해 주세요.';

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
    const [elevators, setElevators] = useState<Elevator[]>([]);
    // 소셜 로그인에 실패하고 돌아오면 계정 메뉴(넓은 화면)나 My 탭(좁은 화면)을 열어 알린다.
    const [loginFailed] = useState(() => takeLoginFailure());
    const loginMessage = loginFailed ? LOGIN_FAILED_MESSAGE : undefined;
    // 메뉴에서 고른 탭과 시트 단계. 좁은 화면에서 검색 탭은 시트를 닫는다.
    const [sheet, setSheet] = useState<{ tab: Tab; snap: SheetSnap }>(() => ({
        tab: loginFailed && !wide ? 'my' : 'search',
        snap: 'half',
    }));
    const sheetOpen = !navigating && !wide && sheet.tab !== 'search';
    const searchInput = useRef<HTMLInputElement>(null);
    const [elevatorError, setElevatorError] = useState<string | null>(null);
    // 즐겨찾기·내 장소. 지도에 별 아이콘으로 보인다.
    const savedPlaces = useSavedPlaces();
    // 계단을 못 쓰는 이동 조건이면 역인 출발·도착을 그 역 엘리베이터로 바꿔 경로를 찾는다.
    const elevatorRoute = useMemo(
        () => toElevatorEndpoints(endpoints, preset, elevators),
        [endpoints, preset, elevators],
    );
    const start = elevatorRoute.endpoints.start?.position ?? null;
    const goal = elevatorRoute.endpoints.goal?.position ?? null;
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

    // 저장한 장소는 이름·주소를 저장해 두었으므로 다시 찾지 않고 카드를 띄운다.
    const showSavedPlace = useCallback((place: SavedPlace) => {
        latestClick.current = place.position;
        setPicked({
            position: place.position,
            name: place.name,
            address: place.address,
        });
    }, []);

    // 저장 탭에서 고르면 지도를 그 장소로 옮기고, 카드가 보이게 시트를 접는다.
    const handleSelectSavedPlace = useCallback(
        (place: SavedPlace) => {
            showSavedPlace(place);
            const [lng, lat] = place.position;
            setFocus([lng, lat]);
            setSheet((current) => ({ ...current, snap: 'collapsed' }));
        },
        [showSavedPlace],
    );

    // 위 검색창에서 고른 장소. 지도를 옮기고 장소 카드를 띄운다.
    const showSearchedPlace = useCallback((place: PickedPlace) => {
        latestClick.current = place.position;
        setPicked(place);
        const [lng, lat] = place.position;
        setFocus([lng, lat]);
        setSheet((current) => ({ ...current, snap: 'collapsed' }));
    }, []);

    const handleSelectTab = (next: Tab) => {
        // 검색 탭을 한 번 더 누르면 검색창에 포커스를 준다.
        if (next === 'search' && sheet.tab === 'search') {
            searchInput.current?.focus();
        }
        setSheet((current) => selectTab(current, next));
    };

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
            setSheet({ tab: 'route', snap: 'half' });
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
            setSheet({ tab: 'route', snap: 'half' });
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

    const searchBox = (
        <TopSearch
            near={mapCenter}
            inputRef={searchInput}
            onPickPlace={showSearchedPlace}
            onSelectRoute={handleSelectRoute}
            inline={wide}
        />
    );
    const savedList = (
        <SavedPanel
            places={savedPlaces.places}
            available={savedPlaces.available}
            error={savedPlaces.error}
            onSelect={handleSelectSavedPlace}
            onDelete={savedPlaces.remove}
        />
    );
    // 탭마다 패널(넓은 화면)이나 시트(좁은 화면)에 보일 내용
    const tabContent: Record<Tab, ReactNode> = {
        search: searchBox,
        route: (
            <>
                <PlaceSearch
                    endpoints={endpoints}
                    near={mapCenter}
                    onSelect={handleSelect}
                    onSelectRoute={handleSelectRoute}
                    onLocate={setMyLocation}
                />
                <RoutePanel
                    preset={preset}
                    endpoints={endpoints}
                    route={route}
                    notes={elevatorRoute.stops.map(elevatorStopText)}
                    onPresetChange={setPreset}
                    onReset={() => setEndpoints(NO_ENDPOINTS)}
                    onStartNavigation={startNavigation}
                />
            </>
        ),
        saved: savedList,
        // 즐겨찾기·내 장소를 함께 보인다. 넓은 화면은 로그인을 오른쪽 위 계정 메뉴에 둔다.
        my: (
            <div className="my-tab">
                {savedList}
                {!wide && (
                    <section className="my-tab__account" aria-label="계정">
                        <h3 className="saved-panel__title">계정</h3>
                        <AccountPanel
                            initialMessage={loginMessage}
                            onSessionChange={savedPlaces.reload}
                        />
                    </section>
                )}
            </div>
        ),
    };
    const showPanel = wide && !navigating;

    return (
        <div
            className="app"
            // 좁은 화면은 지도가 메뉴·시트 위에서 끝난다(index.css).
            data-sheet={sheetOpen ? sheet.snap : 'closed'}
            data-navigating={navigating || undefined}
        >
            {!showPanel && <h1 className="visually-hidden">베리어프리</h1>}
            <MapView
                center={focus ?? undefined}
                start={start}
                goal={goal}
                picked={picked?.position}
                popup={
                    picked && (
                        <PlaceInfoCard
                            // 다른 장소를 고르면 펼친 이름 칸을 닫는다.
                            key={picked.position.join(',')}
                            place={picked}
                            note={elevatorExitsText(
                                stationElevators(
                                    picked.name ?? '',
                                    picked.position,
                                    elevators,
                                ),
                            )}
                            saved={placesAt(
                                savedPlaces.places,
                                picked.position,
                            )}
                            onSave={
                                savedPlaces.available
                                    ? (kind, label) =>
                                          savedPlaces.add(
                                              toSavedPlaceRequest(
                                                  picked,
                                                  kind,
                                                  label,
                                              ),
                                          )
                                    : undefined
                            }
                            onUnsave={savedPlaces.remove}
                            saveError={savedPlaces.error}
                            onPick={handlePick}
                            onClose={() => setPicked(null)}
                        />
                    )
                }
                path={shownRoute?.coordinates ?? null}
                startEntrance={shownRoute?.start_entrance}
                goalEntrance={shownRoute?.goal_entrance}
                savedPlaces={savedPlaces.places}
                fitPadding={wide ? FIT_PADDING.wide : FIT_PADDING.narrow}
                fitRoute={!navigating}
                follow={
                    navigating && following
                        ? (navigationFix?.position ?? null)
                        : null
                }
                // 안내 중에는 지도를 눌러도 출발·도착을 바꾸지 않는다.
                onMapClick={navigating ? undefined : handleMapClick}
                onSavedPlaceClick={navigating ? undefined : showSavedPlace}
                onCenterChange={setMapCenter}
                onDragStart={stopFollowing}
                myLocation={navigationFix ?? myLocation}
            />
            {showPanel && (
                <aside className="side-panel" aria-label="메뉴">
                    <header className="side-panel__header">
                        <h1 className="side-panel__title">베리어프리</h1>
                        <MenuBar tab={sheet.tab} onSelect={handleSelectTab} />
                    </header>
                    <div className="side-panel__body">
                        {tabContent[sheet.tab]}
                    </div>
                </aside>
            )}
            {showPanel && (
                <AccountMenu
                    initialMessage={loginMessage}
                    onSessionChange={savedPlaces.reload}
                />
            )}
            {!wide && !navigating && searchBox}
            {navigating && (
                <NavigationPanel
                    route={route}
                    navigation={navigation}
                    following={following}
                    voice={voice}
                    onVoiceChange={speechSupported ? changeVoice : undefined}
                    onStop={stopNavigation}
                />
            )}
            {sheetOpen && sheet.tab !== 'search' && (
                <BottomSheet
                    title={SHEET_TITLES[sheet.tab]}
                    snap={sheet.snap}
                    onSnapChange={(snap) =>
                        setSheet((current) => ({ ...current, snap }))
                    }
                >
                    {tabContent[sheet.tab]}
                </BottomSheet>
            )}
            {!wide && !navigating && (
                <MenuBar tab={sheet.tab} onSelect={handleSelectTab} />
            )}
            <MyLocationControl
                onLocate={showMyLocation}
                locate={
                    navigationFix
                        ? () => Promise.resolve(navigationFix)
                        : undefined
                }
            />
            {elevatorError && (
                <p role="alert" className="map-view__error">
                    {elevatorError}
                </p>
            )}
        </div>
    );
}
