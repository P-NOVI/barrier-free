import { useId, useState } from 'react';

import { useDebouncedValue } from '../hooks/useDebouncedValue';
import { usePlaceSearch } from '../hooks/usePlaceSearch';
import type { LngLat } from '../lib/kakaoMap';
import type { Place } from '../lib/placeApi';
import {
    LABEL_MAX_LENGTH,
    type SavedPlace,
    type SavedPlaceRequest,
} from '../lib/savedPlacesApi';
import {
    MY_LIST_ICONS as ICONS,
    MY_PLACE_SLOTS as SLOTS,
} from '../lib/myListIcons';
import MyListRow from './MyListRow';
import { SearchResults } from './PlaceSearch';

// 입력을 멈추고 이만큼 지나면 검색한다.
const SEARCH_DELAY_MS = 300;
// 집·회사 말고 더 둘 수 있는 내 장소 수
const FREQUENT_MAX = 5;
const EMPTY_DETAIL = '주소를 등록하시면 길찾기가 쉬워집니다';

const SLOT_LABELS = SLOTS.map((slot) => slot.label);

type MyPlacesProps = {
    /** 내 장소(kind=mine)만 */
    places: SavedPlace[];
    /** 등록할 장소를 찾을 때 이 근처를 앞에 둔다. */
    near: LngLat;
    onSelect: (place: SavedPlace) => void;
    onDelete: (id: number) => void;
    onAdd: (entry: SavedPlaceRequest) => void;
};

function detailOf(place: SavedPlace): string {
    return place.address ? `${place.name} · ${place.address}` : place.name;
}

/** My 탭의 내 장소: 집, 회사/학교, 자주 가는 장소. 빈 칸을 누르면 장소를 찾아 등록한다. */
export default function MyPlaces({
    places,
    near,
    onSelect,
    onDelete,
    onAdd,
}: MyPlacesProps) {
    // 등록 중인 칸. null 이면 자주 가는 장소를 장소 이름으로 등록한다.
    const [registering, setRegistering] = useState<{
        label: string | null;
        title: string;
    } | null>(null);
    const frequent = places.filter(
        (place) => place.label && !SLOT_LABELS.includes(place.label),
    );

    if (registering) {
        return (
            <PlaceRegister
                title={registering.title}
                near={near}
                onCancel={() => setRegistering(null)}
                onPick={(place) => {
                    onAdd({
                        kind: 'mine',
                        label:
                            registering.label ??
                            place.name.slice(0, LABEL_MAX_LENGTH),
                        name: place.name,
                        address: place.road_address || place.address || null,
                        position: place.position,
                    });
                    setRegistering(null);
                }}
            />
        );
    }

    return (
        <>
            <ul className="my-list">
                {SLOTS.map((slot) => {
                    const place = places.find(
                        (saved) => saved.label === slot.label,
                    );
                    return place ? (
                        <MyListRow
                            key={slot.label}
                            icon={slot.icon}
                            title={slot.title}
                            detail={detailOf(place)}
                            onPick={() => onSelect(place)}
                            onDelete={() => onDelete(place.id)}
                        />
                    ) : (
                        <MyListRow
                            key={slot.label}
                            icon={slot.icon}
                            title={slot.title}
                            detail={EMPTY_DETAIL}
                            empty
                            onPick={() => setRegistering(slot)}
                        />
                    );
                })}
            </ul>
            <h3 className="my-tab__heading">
                자주 가는 장소 ({frequent.length}/{FREQUENT_MAX})
            </h3>
            <ul className="my-list">
                {frequent.map((place) => (
                    <MyListRow
                        key={place.id}
                        icon={ICONS.pin}
                        title={place.label ?? place.name}
                        detail={detailOf(place)}
                        onPick={() => onSelect(place)}
                        onDelete={() => onDelete(place.id)}
                    />
                ))}
                {frequent.length < FREQUENT_MAX && (
                    <MyListRow
                        icon={ICONS.add}
                        title="장소 등록"
                        detail={EMPTY_DETAIL}
                        empty
                        onPick={() =>
                            setRegistering({
                                label: null,
                                title: '자주 가는 장소',
                            })
                        }
                    />
                )}
            </ul>
        </>
    );
}

type PlaceRegisterProps = {
    title: string;
    near: LngLat;
    onCancel: () => void;
    onPick: (place: Place) => void;
};

/** 내 장소로 등록할 장소 찾기 */
function PlaceRegister({ title, near, onCancel, onPick }: PlaceRegisterProps) {
    const [text, setText] = useState('');
    const query = useDebouncedValue(text, SEARCH_DELAY_MS);
    const search = usePlaceSearch(query, near);
    const listId = useId();

    return (
        <section className="my-register" aria-label={`${title} 등록`}>
            <div className="my-register__header">
                <button
                    type="button"
                    className="my-register__back"
                    aria-label="등록 그만두기"
                    onClick={onCancel}
                >
                    ‹
                </button>
                <h3 className="my-register__title">{title} 등록</h3>
            </div>
            <input
                className="my-register__input"
                type="search"
                value={text}
                placeholder="장소, 주소 검색"
                aria-label={`${title}로 등록할 장소 검색`}
                aria-controls={listId}
                autoComplete="off"
                autoFocus
                onChange={(event) => setText(event.target.value)}
                onKeyDown={(event) => {
                    if (event.key === 'Escape') {
                        onCancel();
                    }
                }}
            />
            <div aria-live="polite">
                <SearchResults
                    listId={listId}
                    search={search}
                    onPick={onPick}
                />
            </div>
        </section>
    );
}
