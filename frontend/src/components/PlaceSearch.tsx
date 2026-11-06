import {
    type MouseEvent,
    type ReactNode,
    useId,
    useRef,
    useState,
} from 'react';

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
import { MY_PLACE_SLOTS } from '../lib/myListIcons';
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
};

type LocateState =
    | { status: 'idle' }
    | { status: 'locating' }
    // 출발지가 다른 방법으로 바뀌면 오류 안내를 감추려고 그때의 출발지를 같이 둔다.
    | { status: 'error'; message: string; start: Endpoint | null };

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
                            <button type="button" onClick={() => onPick(place)}>
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

// 목록을 눌러도 입력창 포커스가 남아 목록이 닫히지 않게 한다.
function keepFocus(event: MouseEvent) {
    event.preventDefault();
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
    action,
    onSelect,
    onSelectRoute,
}: {
    role: EndpointRole;
    endpoint: Endpoint | null;
    near: LngLat | null;
    action?: ReactNode;
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
                        onFocus={() => setListOpen(true)}
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
                {action}
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
    const focusedRole = (): EndpointRole | null => {
        const active = document.activeElement;
        const section = rowRef.current?.closest('.place-search');
        if (!(active instanceof HTMLElement) || !section?.contains(active)) {
            return null;
        }
        const { role } = active.dataset;
        return isEndpointRole(role) ? role : null;
    };

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
}: PlaceSearchProps) {
    const [locate, setLocate] = useState<LocateState>({ status: 'idle' });

    const locateStart = () => {
        setLocate({ status: 'locating' });
        getCurrentPosition()
            .then((fix) => {
                setLocate({ status: 'idle' });
                onSelect('start', {
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
                    start: endpoints.start,
                }),
            );
    };

    return (
        <section className="place-search" aria-label="출발지·도착지 검색">
            <PlaceField
                key={fieldKey('start', endpoints.start)}
                role="start"
                endpoint={endpoints.start}
                near={near}
                onSelect={(endpoint) => onSelect('start', endpoint)}
                onSelectRoute={onSelectRoute}
                action={
                    <button
                        type="button"
                        className="place-search__locate"
                        disabled={locate.status === 'locating'}
                        onClick={locateStart}
                    >
                        {locate.status === 'locating'
                            ? '찾는 중…'
                            : CURRENT_LOCATION_LABEL}
                    </button>
                }
            />
            {locate.status === 'error' && locate.start === endpoints.start && (
                <p role="alert" className="place-search__error">
                    {locate.message}
                </p>
            )}
            <PlaceField
                key={fieldKey('goal', endpoints.goal)}
                role="goal"
                endpoint={endpoints.goal}
                near={near}
                onSelect={(endpoint) => onSelect('goal', endpoint)}
                onSelectRoute={onSelectRoute}
            />
            {myPlaces && (
                <MyPlaceShortcuts
                    places={myPlaces}
                    endpoints={endpoints}
                    onSelect={onSelect}
                />
            )}
        </section>
    );
}
