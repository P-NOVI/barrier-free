import { type MouseEvent, useId, useRef, useState } from 'react';

import { useDebouncedValue } from '../hooks/useDebouncedValue';
import { type PlaceSearchState, usePlaceSearch } from '../hooks/usePlaceSearch';
import {
    type RecentHistory,
    useRecentHistory,
} from '../hooks/useRecentHistory';
import { formatDistance } from '../lib/format';
import { getCurrentPosition, type LocationFix } from '../lib/geolocation';
import {
    addSearch,
    recentPlaces,
    type RouteHistory,
    type SearchHistory,
    searchEndpoint,
    toSearchEntry,
} from '../lib/historyApi';
import type { LngLat } from '../lib/kakaoMap';
import { MY_LIST_ICONS, MY_PLACE_SLOTS } from '../lib/myListIcons';
import type { Place } from '../lib/placeApi';
import { presetLabel } from '../lib/presets';
import type { SavedPlace } from '../lib/savedPlacesApi';
import {
    CURRENT_LOCATION_LABEL,
    type Endpoint,
    type EndpointRole,
    type Endpoints,
    isEndpointRole,
    shortcutRole,
} from '../lib/selection';

// 입력을 멈추고 이만큼 지나면 검색한다.
const SEARCH_DELAY_MS = 300;
// 검색창을 누르면 보일 최근 기록 수
const RECENT_ROUTES = 3;
const RECENT_PLACES = 5;

const FIELD_LABELS: Record<EndpointRole, string> = {
    start: '출발지',
    goal: '도착지',
};

type PlaceSearchProps = {
    endpoints: Endpoints;
    /** 이 근처 장소를 앞에 두고 거리를 함께 보인다. */
    near: LngLat;
    onSelect: (role: EndpointRole, endpoint: Endpoint) => void;
    /** 최근 경로를 고르면 출발·도착을 함께 바꾼다. */
    onSelectRoute: (entry: RouteHistory) => void;
    /** 현재 위치를 찾으면 알린다. 지도에 내 위치로 표시한다. */
    onLocate: (fix: LocationFix) => void;
    /** 내 장소. 있으면 입력칸 아래에 집·회사 버튼을 둔다(못 불러왔으면 숨김). */
    myPlaces?: SavedPlace[];
    /** 즐겨찾기 버튼으로 고를 장소. 없으면 못 불러온 것이다. */
    favorites?: SavedPlace[];
    /** 지도를 눌러 고르는 중인 칸 */
    mapPick?: EndpointRole | null;
    /** 지도에서 선택을 시작(칸)하거나 그만둔다(null). 없으면 버튼을 숨긴다. */
    onMapPickChange?: (role: EndpointRole | null) => void;
};

type LocateState =
    | { status: 'idle' }
    | { status: 'locating' }
    // 출발·도착이 다른 방법으로 바뀌면 오류 안내를 감추려고 그때의 출발·도착을 같이 둔다.
    | { status: 'error'; message: string; endpoints: Endpoints };

// 입력칸 아래 버튼 아이콘(24×24 선)
const ACTION_ICONS = {
    locate: 'M20 4 4 11l7 2 2 7Z',
    map: 'M9 4 3 6v14l6-2 6 2 6-2V4l-6 2ZM9 4v14M15 6v14',
    star: MY_LIST_ICONS.star,
};

// 목록을 눌러도 입력창 포커스가 남아 목록이 닫히지 않게 한다.
// iPhone(Safari·홈 화면 앱)은 버튼을 눌러도 버튼에 포커스가 가지 않아, 이것이 없으면
// 입력창 blur 로 목록이 먼저 사라져 누른 항목이 선택되지 않는다.
function keepFocus(event: MouseEvent) {
    event.preventDefault();
}

export function SearchResults({
    listId,
    search,
    onPick,
}: {
    listId: string;
    search: PlaceSearchState;
    onPick: (place: Place) => void;
}) {
    switch (search.status) {
        case 'idle':
            return null;
        case 'loading':
            return <p className="place-search__message">찾는 중…</p>;
        case 'error':
            return (
                <p role="alert" className="place-search__error">
                    {search.message}
                </p>
            );
        case 'success':
            if (search.places.length === 0) {
                return (
                    <p className="place-search__message">
                        검색 결과가 없습니다.
                    </p>
                );
            }
            return (
                <ul id={listId} className="place-search__results">
                    {search.places.map((place) => (
                        <li key={`${place.name}@${place.position}`}>
                            <button
                                type="button"
                                onMouseDown={keepFocus}
                                onClick={() => onPick(place)}
                            >
                                <span className="place-search__name">
                                    {place.name}
                                </span>
                                <span className="place-search__address">
                                    {place.road_address || place.address}
                                    {place.distance_m !== null &&
                                        ` · ${formatDistance(place.distance_m)}`}
                                </span>
                            </button>
                        </li>
                    ))}
                </ul>
            );
    }
}

function RecentItem({
    name,
    detail,
    onPick,
    onRemove,
}: {
    name: string;
    detail: string | null;
    onPick: () => void;
    onRemove: () => void;
}) {
    return (
        <li className="place-search__recent-item">
            <button type="button" onMouseDown={keepFocus} onClick={onPick}>
                <span className="place-search__name">{name}</span>
                {detail && (
                    <span className="place-search__address">{detail}</span>
                )}
            </button>
            <button
                type="button"
                className="place-search__remove"
                aria-label={`${name} 기록 지우기`}
                onMouseDown={keepFocus}
                onClick={onRemove}
            >
                ×
            </button>
        </li>
    );
}

export function RecentList({
    listId,
    recent,
    onPickSearch,
    onPickRoute,
}: {
    listId: string;
    recent: RecentHistory;
    onPickSearch: (entry: SearchHistory) => void;
    onPickRoute: (entry: RouteHistory) => void;
}) {
    const routes = recent.routes.slice(0, RECENT_ROUTES);
    const places = recentPlaces(recent.searches, RECENT_PLACES);
    if (routes.length === 0 && places.length === 0) {
        return null;
    }
    return (
        <div id={listId} className="place-search__recent">
            {routes.length > 0 && (
                <>
                    <p className="place-search__recent-title">최근 경로</p>
                    <ul className="place-search__results">
                        {routes.map((entry) => (
                            <RecentItem
                                key={entry.id}
                                name={`${entry.start_name} → ${entry.goal_name}`}
                                detail={`${presetLabel(entry.preset)} · ${formatDistance(entry.distance_m)}`}
                                onPick={() => onPickRoute(entry)}
                                onRemove={() => recent.removeRoute(entry.id)}
                            />
                        ))}
                    </ul>
                </>
            )}
            {places.length > 0 && (
                <>
                    <p className="place-search__recent-title">최근 검색</p>
                    <ul className="place-search__results">
                        {places.map((entry) => (
                            <RecentItem
                                key={entry.id}
                                name={entry.place_name ?? entry.query}
                                detail={entry.address}
                                onPick={() => onPickSearch(entry)}
                                onRemove={() => recent.removeSearch(entry.id)}
                            />
                        ))}
                    </ul>
                </>
            )}
        </div>
    );
}

/** 고른 장소가 바뀌면 부모가 key 로 다시 만들어 입력값을 그 이름으로 맞춘다. */
function PlaceField({
    role,
    endpoint,
    near,
    onFocus,
    onSelect,
    onSelectRoute,
}: {
    role: EndpointRole;
    endpoint: Endpoint | null;
    near: LngLat | null;
    /** 입력칸을 누르면 알린다. */
    onFocus: () => void;
    onSelect: (endpoint: Endpoint) => void;
    onSelectRoute: (entry: RouteHistory) => void;
}) {
    const label = FIELD_LABELS[role];
    const [text, setText] = useState(endpoint?.label ?? '');
    // 사용자가 입력을 고친 뒤에만 검색한다.
    const [editing, setEditing] = useState(false);
    // 입력창을 누르면 열고, 포커스가 이 칸 밖으로 나가면 닫는다.
    const [listOpen, setListOpen] = useState(false);
    const typing = editing && text.trim() !== '';
    const query = useDebouncedValue(editing ? text : '', SEARCH_DELAY_MS);
    const search = usePlaceSearch(query, near);
    // 검색어가 없을 때는 검색 결과 대신 최근 기록을 보인다.
    const recent = useRecentHistory(listOpen && !typing);
    const listId = useId();

    const choose = (endpoint: Endpoint) => {
        setText(endpoint.label);
        setEditing(false);
        setListOpen(false);
        onSelect(endpoint);
    };

    const pick = (place: Place) => {
        // 기록을 못 남겨도 고른 장소는 그대로 쓴다.
        addSearch(toSearchEntry(text, place)).catch(() => undefined);
        choose({ position: place.position, label: place.name });
    };

    const pickRecent = (entry: SearchHistory) => {
        const picked = searchEndpoint(entry);
        if (!picked) {
            return;
        }
        // 다시 고른 기록은 맨 앞으로 옮긴다.
        addSearch({
            query: entry.query,
            place_name: entry.place_name,
            address: entry.address,
            position: entry.position,
        }).catch(() => undefined);
        choose(picked);
    };

    const pickRoute = (entry: RouteHistory) => {
        setListOpen(false);
        onSelectRoute(entry);
    };

    return (
        <div
            className="place-search__field"
            onBlur={(event) => {
                if (!event.currentTarget.contains(event.relatedTarget)) {
                    setListOpen(false);
                }
            }}
        >
            <div className="place-search__row">
                <label className="place-search__label">
                    <input
                        type="search"
                        value={text}
                        placeholder={`${label} 입력`}
                        aria-label={label}
                        data-role={role}
                        autoComplete="off"
                        aria-controls={listId}
                        onFocus={() => {
                            setListOpen(true);
                            onFocus();
                        }}
                        onClick={() => setListOpen(true)}
                        onChange={(event) => {
                            setText(event.target.value);
                            setEditing(true);
                        }}
                        onKeyDown={(event) => {
                            if (event.key === 'Escape') {
                                setText(endpoint?.label ?? '');
                                setEditing(false);
                                setListOpen(false);
                            }
                        }}
                    />
                </label>
            </div>
            {/* 검색 결과·최근 기록은 두 입력칸과 내 장소 버튼 아래에 연다(index.css). */}
            <div className="place-search__dropdown">
                {typing && (
                    <div aria-live="polite">
                        <SearchResults
                            listId={listId}
                            search={search}
                            onPick={pick}
                        />
                    </div>
                )}
                {listOpen && !typing && (
                    <RecentList
                        listId={listId}
                        recent={recent}
                        onPickSearch={pickRecent}
                        onPickRoute={pickRoute}
                    />
                )}
            </div>
        </div>
    );
}

/** section 안에서 포커스가 있는 입력칸(출발지·도착지). 없으면 null */
function focusedRoleIn(
    section: Element | null | undefined,
): EndpointRole | null {
    const active = document.activeElement;
    if (!(active instanceof HTMLElement) || !section?.contains(active)) {
        return null;
    }
    const { role } = active.dataset;
    return isEndpointRole(role) ? role : null;
}

/** 입력칸 아래 집·회사 버튼. 누르면 그 장소를 출발지나 도착지에 넣는다. */
function MyPlaceShortcuts({
    places,
    endpoints,
    onSelect,
}: {
    places: SavedPlace[];
    endpoints: Endpoints;
    onSelect: (role: EndpointRole, endpoint: Endpoint) => void;
}) {
    const rowRef = useRef<HTMLDivElement>(null);
    // 아직 등록하지 않은 칸을 눌렀을 때 그 칸 label
    const [missing, setMissing] = useState<string | null>(null);
    const slots = MY_PLACE_SLOTS.map((slot) => ({
        ...slot,
        place: places.find((saved) => saved.label === slot.label),
    }));
    const missingSlot = slots.find(
        (slot) => slot.label === missing && !slot.place,
    );

    // 버튼을 눌러도 포커스가 입력칸에 남아(keepFocus) 누르고 있던 칸을 알 수 있다.
    const focusedRole = () =>
        focusedRoleIn(rowRef.current?.closest('.place-search'));

    return (
        <>
            <div ref={rowRef} className="place-search__shortcuts">
                {slots.map(({ label, title, icon, place }) => (
                    <button
                        key={label}
                        type="button"
                        className="place-search__shortcut"
                        data-empty={place ? undefined : true}
                        aria-label={
                            place
                                ? `${title}: ${place.address ?? place.name}`
                                : `${title} (등록 안 됨)`
                        }
                        onMouseDown={keepFocus}
                        onClick={() => {
                            if (!place) {
                                setMissing(label);
                                return;
                            }
                            setMissing(null);
                            // 지도의 내 장소 표시처럼 칸 이름(집·회사)으로 넣는다.
                            onSelect(shortcutRole(focusedRole(), endpoints), {
                                position: place.position,
                                label,
                            });
                        }}
                    >
                        <span
                            className="place-search__shortcut-icon"
                            aria-hidden="true"
                        >
                            <svg viewBox="0 0 24 24">
                                <path d={icon} />
                            </svg>
                        </span>
                        {label}
                    </button>
                ))}
            </div>
            {missingSlot && (
                <p role="alert" className="place-search__message">
                    {missingSlot.title} 주소가 없습니다. My 탭 내 장소에서
                    등록하세요.
                </p>
            )}
        </>
    );
}

/** 입력칸 아래 내 위치·지도에서 선택·즐겨찾기 버튼 한 칸 */
function ActionButton({
    icon,
    label,
    disabled,
    pressed,
    expanded,
    onMouseDown,
    onClick,
}: {
    icon: string;
    label: string;
    disabled?: boolean;
    pressed?: boolean;
    expanded?: boolean;
    onMouseDown: () => void;
    onClick: () => void;
}) {
    return (
        <button
            type="button"
            className="place-search__action"
            disabled={disabled}
            aria-pressed={pressed}
            aria-expanded={expanded}
            onMouseDown={onMouseDown}
            onClick={onClick}
        >
            <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d={icon} />
            </svg>
            {label}
        </button>
    );
}

/** 즐겨찾기 버튼을 누르면 입력칸 아래에 여는 목록. places 가 없으면 못 불러온 것이다. */
function FavoriteList({
    role,
    places,
    onPick,
}: {
    role: EndpointRole;
    places: SavedPlace[] | undefined;
    onPick: (place: SavedPlace) => void;
}) {
    const title = (
        <p className="place-search__recent-title">
            즐겨찾기에서 {FIELD_LABELS[role]} 고르기
        </p>
    );
    if (!places) {
        return (
            <>
                {title}
                <p className="place-search__message">
                    즐겨찾기를 불러오지 못했습니다.
                </p>
            </>
        );
    }
    if (places.length === 0) {
        return (
            <>
                {title}
                <p className="place-search__message">
                    즐겨찾기한 장소가 없습니다. 지도에서 장소를 누르고 장소
                    카드의 북마크에서 즐겨찾기를 눌러 추가하세요.
                </p>
            </>
        );
    }
    return (
        <>
            {title}
            <ul className="place-search__results">
                {places.map((place) => (
                    <li key={place.id}>
                        <button type="button" onClick={() => onPick(place)}>
                            <span className="place-search__name">
                                {place.name}
                            </span>
                            {place.address && (
                                <span className="place-search__address">
                                    {place.address}
                                </span>
                            )}
                        </button>
                    </li>
                ))}
            </ul>
        </>
    );
}

function fieldKey(role: EndpointRole, endpoint: Endpoint | null): string {
    return endpoint ? `${role}:${endpoint.label}@${endpoint.position}` : role;
}

export default function PlaceSearch({
    endpoints,
    near,
    onSelect,
    onSelectRoute,
    onLocate,
    myPlaces,
    favorites,
    mapPick = null,
    onMapPickChange,
}: PlaceSearchProps) {
    const sectionRef = useRef<HTMLElement>(null);
    const [locate, setLocate] = useState<LocateState>({ status: 'idle' });
    // 즐겨찾기 목록을 열었을 때, 고른 장소를 넣을 칸
    const [favoritesFor, setFavoritesFor] = useState<EndpointRole | null>(null);
    // 아래 버튼을 누르는 순간 포커스가 있던 입력칸. 누르면 입력칸에서 포커스가 빠지므로
    // (휴대폰 키보드도 내려간다) 누르기 시작할 때(mousedown) 기억해 둔다.
    const pressedRole = useRef<EndpointRole | null>(null);
    const rememberRole = () => {
        pressedRole.current = focusedRoleIn(sectionRef.current);
    };
    // 누르고 있던 칸. 없으면(키보드로 눌렀거나 칸을 누르지 않음) null
    const takeRole = (): EndpointRole | null => {
        const role = pressedRole.current ?? focusedRoleIn(sectionRef.current);
        pressedRole.current = null;
        return role;
    };

    // 내 위치는 누르고 있던 칸, 없으면 출발지에 넣는다.
    const locateHere = () => {
        const role = takeRole() ?? 'start';
        setFavoritesFor(null);
        setLocate({ status: 'locating' });
        getCurrentPosition()
            .then((fix) => {
                setLocate({ status: 'idle' });
                onSelect(role, {
                    position: fix.position,
                    label: CURRENT_LOCATION_LABEL,
                });
                onLocate(fix);
            })
            .catch((error: unknown) =>
                setLocate({
                    status: 'error',
                    message:
                        error instanceof Error ? error.message : String(error),
                    endpoints,
                }),
            );
    };

    // 지도에서 선택·즐겨찾기는 누르고 있던 칸, 없으면 집·회사 버튼처럼 빈 칸에 넣는다.
    const toggleMapPick = () => {
        const role = shortcutRole(takeRole(), endpoints);
        setFavoritesFor(null);
        onMapPickChange?.(mapPick ? null : role);
    };

    const toggleFavorites = () => {
        const role = shortcutRole(takeRole(), endpoints);
        setFavoritesFor((current) => (current ? null : role));
        if (mapPick) {
            onMapPickChange?.(null);
        }
    };

    // 입력칸을 다시 누르면 즐겨찾기 목록과 지도에서 선택을 닫고 검색·최근 기록을 보인다.
    const handleFieldFocus = () => {
        setFavoritesFor(null);
        if (mapPick) {
            onMapPickChange?.(null);
        }
    };

    return (
        <section
            ref={sectionRef}
            className="place-search"
            aria-label="출발지·도착지 검색"
        >
            <PlaceField
                key={fieldKey('start', endpoints.start)}
                role="start"
                endpoint={endpoints.start}
                near={near}
                onFocus={handleFieldFocus}
                onSelect={(endpoint) => onSelect('start', endpoint)}
                onSelectRoute={onSelectRoute}
            />
            <PlaceField
                key={fieldKey('goal', endpoints.goal)}
                role="goal"
                endpoint={endpoints.goal}
                near={near}
                onFocus={handleFieldFocus}
                onSelect={(endpoint) => onSelect('goal', endpoint)}
                onSelectRoute={onSelectRoute}
            />
            <div className="place-search__actions">
                <ActionButton
                    icon={ACTION_ICONS.locate}
                    label={
                        locate.status === 'locating' ? '찾는 중…' : '내 위치'
                    }
                    disabled={locate.status === 'locating'}
                    onMouseDown={rememberRole}
                    onClick={locateHere}
                />
                {onMapPickChange && (
                    <ActionButton
                        icon={ACTION_ICONS.map}
                        label="지도에서 선택"
                        pressed={mapPick !== null}
                        onMouseDown={rememberRole}
                        onClick={toggleMapPick}
                    />
                )}
                <ActionButton
                    icon={ACTION_ICONS.star}
                    label="즐겨찾기"
                    expanded={favoritesFor !== null}
                    onMouseDown={rememberRole}
                    onClick={toggleFavorites}
                />
            </div>
            {locate.status === 'error' && locate.endpoints === endpoints && (
                <p role="alert" className="place-search__error">
                    {locate.message}
                </p>
            )}
            {myPlaces && (
                <MyPlaceShortcuts
                    places={myPlaces}
                    endpoints={endpoints}
                    onSelect={onSelect}
                />
            )}
            {favoritesFor && (
                <div className="place-search__dropdown">
                    <FavoriteList
                        role={favoritesFor}
                        places={favorites}
                        onPick={(place) => {
                            setFavoritesFor(null);
                            onSelect(favoritesFor, {
                                position: place.position,
                                label: place.name,
                            });
                        }}
                    />
                </div>
            )}
        </section>
    );
}
