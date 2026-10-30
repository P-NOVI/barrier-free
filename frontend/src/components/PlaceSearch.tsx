import { type ReactNode, useId, useState } from 'react';

import { useDebouncedValue } from '../hooks/useDebouncedValue';
import { type PlaceSearchState, usePlaceSearch } from '../hooks/usePlaceSearch';
import { formatDistance } from '../lib/format';
import { getCurrentPosition } from '../lib/geolocation';
import type { LngLat } from '../lib/kakaoMap';
import type { Place } from '../lib/placeApi';
import type { Endpoint, EndpointRole, Endpoints } from '../lib/selection';

// 입력을 멈추고 이만큼 지나면 검색한다.
const SEARCH_DELAY_MS = 300;
const CURRENT_LOCATION_LABEL = '현재 위치';

const FIELD_LABELS: Record<EndpointRole, string> = {
    start: '출발',
    goal: '도착',
};

type PlaceSearchProps = {
    endpoints: Endpoints;
    /** 이 근처 장소를 앞에 두고 거리를 함께 보인다. */
    near: LngLat | null;
    onSelect: (role: EndpointRole, endpoint: Endpoint) => void;
};

type LocateState =
    | { status: 'idle' }
    | { status: 'locating' }
    | { status: 'error'; message: string };

function SearchResults({
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

/** 고른 장소가 바뀌면 부모가 key 로 다시 만들어 입력값을 그 이름으로 맞춘다. */
function PlaceField({
    role,
    endpoint,
    near,
    action,
    onSelect,
}: {
    role: EndpointRole;
    endpoint: Endpoint | null;
    near: LngLat | null;
    action?: ReactNode;
    onSelect: (endpoint: Endpoint) => void;
}) {
    const label = FIELD_LABELS[role];
    const [text, setText] = useState(endpoint?.label ?? '');
    // 사용자가 입력을 고친 뒤에만 검색한다.
    const [editing, setEditing] = useState(false);
    const query = useDebouncedValue(editing ? text : '', SEARCH_DELAY_MS);
    const search = usePlaceSearch(query, near);
    const listId = useId();

    const pick = (place: Place) => {
        setText(place.name);
        setEditing(false);
        onSelect({ position: place.position, label: place.name });
    };

    return (
        <div className="place-search__field">
            <div className="place-search__row">
                <label
                    className={`place-search__label place-search__label--${role}`}
                >
                    <span className="place-search__badge">{label}</span>
                    <input
                        type="search"
                        value={text}
                        placeholder={`${label}지 이름이나 주소`}
                        autoComplete="off"
                        aria-controls={listId}
                        onChange={(event) => {
                            setText(event.target.value);
                            setEditing(true);
                        }}
                        onKeyDown={(event) => {
                            if (event.key === 'Escape') {
                                setText(endpoint?.label ?? '');
                                setEditing(false);
                            }
                        }}
                    />
                </label>
                {action}
            </div>
            {editing && (
                <div aria-live="polite">
                    <SearchResults
                        listId={listId}
                        search={search}
                        onPick={pick}
                    />
                </div>
            )}
        </div>
    );
}

function fieldKey(role: EndpointRole, endpoint: Endpoint | null): string {
    return endpoint ? `${role}:${endpoint.label}@${endpoint.position}` : role;
}

export default function PlaceSearch({
    endpoints,
    near,
    onSelect,
}: PlaceSearchProps) {
    const [locate, setLocate] = useState<LocateState>({ status: 'idle' });

    const locateStart = () => {
        setLocate({ status: 'locating' });
        getCurrentPosition()
            .then((position) => {
                setLocate({ status: 'idle' });
                onSelect('start', {
                    position,
                    label: CURRENT_LOCATION_LABEL,
                });
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
        <section className="place-search" aria-label="출발지·도착지 검색">
            <PlaceField
                key={fieldKey('start', endpoints.start)}
                role="start"
                endpoint={endpoints.start}
                near={near}
                onSelect={(endpoint) => onSelect('start', endpoint)}
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
            {locate.status === 'error' && (
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
            />
        </section>
    );
}
