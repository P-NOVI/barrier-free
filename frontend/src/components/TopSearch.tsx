import { type Ref, useId, useState } from 'react';

import { useDebouncedValue } from '../hooks/useDebouncedValue';
import { usePlaceSearch } from '../hooks/usePlaceSearch';
import { useRecentHistory } from '../hooks/useRecentHistory';
import {
    addSearch,
    type RouteHistory,
    type SearchHistory,
    toSearchEntry,
} from '../lib/historyApi';
import type { LngLat } from '../lib/kakaoMap';
import type { Place } from '../lib/placeApi';
import { categoryLabel, type PickedPlace } from '../lib/selection';
import { RecentList, SearchResults } from './PlaceSearch';

// 입력을 멈추고 이만큼 지나면 검색한다.
const SEARCH_DELAY_MS = 300;

type TopSearchProps = {
    /** 이 근처 장소를 앞에 두고 거리를 함께 보인다. */
    near: LngLat;
    /** 아래 메뉴의 검색을 누르면 이 입력창에 포커스를 준다. */
    inputRef?: Ref<HTMLInputElement>;
    /** 고른 장소. 지도에 장소 카드로 보인다. */
    onPickPlace: (place: PickedPlace) => void;
    /** 최근 경로를 고르면 출발·도착을 함께 바꾼다. */
    onSelectRoute: (entry: RouteHistory) => void;
    /** true 면 왼쪽 패널 안에 두고, 최근 기록·검색 결과를 늘 펼쳐 둔다(넓은 화면). */
    inline?: boolean;
};

/** 장소 검색창. 누르면 최근 경로·최근 검색이 아래로 펼쳐진다. */
export default function TopSearch({
    near,
    inputRef,
    onPickPlace,
    onSelectRoute,
    inline = false,
}: TopSearchProps) {
    const [text, setText] = useState('');
    // 사용자가 입력을 고친 뒤에만 검색한다.
    const [editing, setEditing] = useState(false);
    // 입력창을 누르면 열고, 포커스가 검색창 밖으로 나가면 닫는다.
    const [opened, setOpened] = useState(false);
    const listOpen = inline || opened;
    const typing = editing && text.trim() !== '';
    const query = useDebouncedValue(editing ? text : '', SEARCH_DELAY_MS);
    const search = usePlaceSearch(query, near);
    // 검색어가 없을 때는 검색 결과 대신 최근 기록을 보인다.
    const recent = useRecentHistory(listOpen && !typing);
    const listId = useId();

    const close = (label: string) => {
        setText(label);
        setEditing(false);
        setOpened(false);
        // 휴대폰 키보드를 내려 지도와 장소 카드가 보이게 한다.
        if (document.activeElement instanceof HTMLElement) {
            document.activeElement.blur();
        }
    };

    const pick = (place: Place) => {
        // 기록을 못 남겨도 고른 장소는 그대로 쓴다.
        addSearch(toSearchEntry(text, place)).catch(() => undefined);
        close(place.name);
        onPickPlace({
            position: place.position,
            name: place.name,
            address: place.road_address || place.address,
            category: categoryLabel(place.category, place.name),
        });
    };

    const pickRecent = (entry: SearchHistory) => {
        if (!entry.position) {
            return;
        }
        // 다시 고른 기록은 맨 앞으로 옮긴다.
        addSearch({
            query: entry.query,
            place_name: entry.place_name,
            address: entry.address,
            position: entry.position,
        }).catch(() => undefined);
        const name = entry.place_name ?? entry.query;
        close(name);
        onPickPlace({
            position: entry.position,
            name,
            address: entry.address,
        });
    };

    const pickRoute = (entry: RouteHistory) => {
        close('');
        onSelectRoute(entry);
    };

    return (
        <div
            role="search"
            className={inline ? 'top-search top-search--inline' : 'top-search'}
            onBlur={(event) => {
                if (!event.currentTarget.contains(event.relatedTarget)) {
                    setOpened(false);
                }
            }}
        >
            <label className="top-search__field">
                <svg
                    className="top-search__icon"
                    viewBox="0 0 24 24"
                    aria-hidden="true"
                >
                    <path d="M10.5 4a6.5 6.5 0 1 0 0 13 6.5 6.5 0 0 0 0-13ZM15.2 15.2 20 20" />
                </svg>
                <input
                    ref={inputRef}
                    type="search"
                    value={text}
                    placeholder="장소, 주소 검색"
                    aria-label="장소 검색"
                    autoComplete="off"
                    aria-controls={listId}
                    onFocus={() => setOpened(true)}
                    onClick={() => setOpened(true)}
                    onChange={(event) => {
                        setText(event.target.value);
                        setEditing(true);
                        setOpened(true);
                    }}
                    onKeyDown={(event) => {
                        if (event.key === 'Escape') {
                            setEditing(false);
                            setOpened(false);
                        }
                    }}
                />
            </label>
            {listOpen && typing && (
                <div className="top-search__list" aria-live="polite">
                    <SearchResults
                        listId={listId}
                        search={search}
                        onPick={pick}
                    />
                </div>
            )}
            {listOpen && !typing && (
                <div className="top-search__list">
                    <RecentList
                        listId={listId}
                        recent={recent}
                        onPickSearch={pickRecent}
                        onPickRoute={pickRoute}
                    />
                </div>
            )}
        </div>
    );
}
