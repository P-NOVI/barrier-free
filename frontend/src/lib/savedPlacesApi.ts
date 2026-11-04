// 즐겨찾기와 내 장소. 쿠키의 사용자(게스트·회원) 것만 오간다.
// 요청·응답 형식은 backend/app/schemas.py 의 SavedPlace* 와 같다.

import { type ApiOptions, requestJson } from './apiClient';
import { inOrder } from './historyApi';
import type { LngLat } from './kakaoMap';
import { MAP_CLICK_LABEL, type PickedPlace } from './selection';

/** favorite 는 별표만 붙인 즐겨찾기, mine 은 이름(집, 회사 등)을 붙인 내 장소 */
export type SavedPlaceKind = 'favorite' | 'mine';

export type SavedPlaceRequest = {
    kind: SavedPlaceKind;
    /** 내 장소 이름. 즐겨찾기는 null */
    label: string | null;
    name: string;
    address: string | null;
    position: LngLat;
};

export type SavedPlace = SavedPlaceRequest & {
    id: number;
    created_at: string;
};

/** 내 장소 이름 중 바로 고를 수 있는 것. 그 밖의 이름은 직접 입력한다. */
export const MY_PLACE_LABELS = ['집', '회사'];
// backend/app/models.py 의 LABEL_MAX_LENGTH 와 같다.
export const LABEL_MAX_LENGTH = 20;

export async function fetchSavedPlaces(
    options?: ApiOptions,
): Promise<SavedPlace[]> {
    const { places } = await requestJson<{ places: SavedPlace[] }>(
        {
            path: '/api/me/places',
            failureMessage: '저장한 장소를 불러오지 못했습니다.',
        },
        options,
    );
    return places;
}

/** 같은 위치의 즐겨찾기, 같은 이름의 내 장소가 있으면 바꿔 저장한다. */
export function addSavedPlace(
    entry: SavedPlaceRequest,
    options?: ApiOptions,
): Promise<SavedPlace> {
    return inOrder(() =>
        requestJson<SavedPlace>(
            {
                path: '/api/me/places',
                body: entry,
                failureMessage: '장소를 저장하지 못했습니다.',
            },
            options,
        ),
    );
}

export function deleteSavedPlace(
    id: number,
    options?: ApiOptions,
): Promise<void> {
    return inOrder(() =>
        requestJson<void>(
            {
                path: `/api/me/places/${id}`,
                method: 'DELETE',
                failureMessage: '장소를 지우지 못했습니다.',
            },
            options,
        ),
    );
}

export function toSavedPlaceRequest(
    place: PickedPlace,
    kind: SavedPlaceKind,
    label: string | null = null,
): SavedPlaceRequest {
    return {
        kind,
        label,
        name: place.name ?? place.address ?? MAP_CLICK_LABEL,
        address: place.address,
        position: place.position,
    };
}

function samePosition([lng, lat]: LngLat, [otherLng, otherLat]: LngLat) {
    return lng === otherLng && lat === otherLat;
}

/** 새로 저장한 saved 때문에 서버에서 지워진 장소인지. 백엔드 place_repository 와 같은 규칙이다. */
export function isReplacedBy(place: SavedPlace, saved: SavedPlace): boolean {
    if (place.id === saved.id) {
        return true;
    }
    if (place.kind !== saved.kind) {
        return false;
    }
    return saved.kind === 'mine'
        ? place.label === saved.label
        : samePosition(place.position, saved.position);
}

export function placesAt(places: SavedPlace[], position: LngLat): SavedPlace[] {
    return places.filter((place) => samePosition(place.position, position));
}

/** 목록·지도에 보일 이름. 내 장소는 붙인 이름을 쓴다. */
export function savedPlaceTitle(place: SavedPlace): string {
    return place.label ?? place.name;
}
