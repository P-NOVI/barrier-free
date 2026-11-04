import { afterEach, describe, expect, it, vi } from 'vitest';

import {
    addSavedPlace,
    deleteSavedPlace,
    fetchSavedPlaces,
    isReplacedBy,
    placesAt,
    type SavedPlace,
    savedPlaceTitle,
    toSavedPlaceRequest,
} from './savedPlacesApi';
import { MAP_CLICK_LABEL } from './selection';

const BASE_URL = 'http://api.test';
const OPTIONS = { baseUrl: BASE_URL };
const SEOUL_STATION: [number, number] = [126.9707, 37.5547];
const CITY_HALL: [number, number] = [126.9779, 37.5663];

function place(id: number, overrides: Partial<SavedPlace> = {}): SavedPlace {
    return {
        id,
        kind: 'favorite',
        label: null,
        name: '서울역',
        address: '서울 용산구 한강대로 405',
        position: SEOUL_STATION,
        created_at: '2026-11-04T00:00:00',
        ...overrides,
    };
}

function jsonResponse(body: unknown, status = 200): Response {
    return new Response(JSON.stringify(body), { status });
}

afterEach(() => {
    vi.unstubAllGlobals();
});

describe('저장 장소 API', () => {
    it('쿠키와 함께 저장한 장소를 받는다', async () => {
        const fetchMock = vi
            .fn()
            .mockResolvedValue(jsonResponse({ places: [place(1)] }));
        vi.stubGlobal('fetch', fetchMock);

        await expect(fetchSavedPlaces(OPTIONS)).resolves.toEqual([place(1)]);

        const [url, init] = fetchMock.mock.calls[0];
        expect(String(url)).toBe('http://api.test/api/me/places');
        expect(init.credentials).toBe('include');
    });

    it('장소를 POST 하고 DELETE 한다', async () => {
        const fetchMock = vi
            .fn()
            .mockResolvedValueOnce(jsonResponse(place(1), 201))
            .mockResolvedValueOnce(new Response(null, { status: 204 }));
        vi.stubGlobal('fetch', fetchMock);
        const entry = toSavedPlaceRequest(
            { position: CITY_HALL, name: '서울시청', address: null },
            'mine',
            '회사',
        );

        await addSavedPlace(entry, OPTIONS);
        await deleteSavedPlace(1, OPTIONS);

        const [postUrl, post] = fetchMock.mock.calls[0];
        expect(String(postUrl)).toBe('http://api.test/api/me/places');
        expect(post.method).toBe('POST');
        expect(JSON.parse(post.body)).toEqual({
            kind: 'mine',
            label: '회사',
            name: '서울시청',
            address: null,
            position: CITY_HALL,
        });
        const [deleteUrl, remove] = fetchMock.mock.calls[1];
        expect(String(deleteUrl)).toBe('http://api.test/api/me/places/1');
        expect(remove.method).toBe('DELETE');
    });

    it('가득 차면 서버 메시지로 실패한다', async () => {
        vi.stubGlobal(
            'fetch',
            vi.fn().mockResolvedValue(
                jsonResponse(
                    {
                        detail: {
                            reason: 'places_full',
                            message: '장소는 100개까지 저장할 수 있습니다.',
                        },
                    },
                    409,
                ),
            ),
        );

        await expect(
            addSavedPlace(
                toSavedPlaceRequest(
                    { position: CITY_HALL, name: '서울시청', address: null },
                    'favorite',
                ),
                OPTIONS,
            ),
        ).rejects.toThrow('100개');
    });
});

describe('toSavedPlaceRequest', () => {
    it('이름이 없으면 주소, 주소도 없으면 지도에서 고른 위치로 저장한다', () => {
        expect(
            toSavedPlaceRequest(
                { position: CITY_HALL, name: null, address: '서울 중구' },
                'favorite',
            ).name,
        ).toBe('서울 중구');
        expect(
            toSavedPlaceRequest(
                { position: CITY_HALL, name: null, address: null },
                'favorite',
            ).name,
        ).toBe(MAP_CLICK_LABEL);
    });
});

describe('isReplacedBy', () => {
    it('같은 위치의 즐겨찾기를 바꾼다', () => {
        expect(isReplacedBy(place(1), place(2))).toBe(true);
        expect(isReplacedBy(place(1), place(2, { position: CITY_HALL }))).toBe(
            false,
        );
    });

    it('같은 이름의 내 장소를 바꾼다', () => {
        const home = place(1, { kind: 'mine', label: '집' });

        expect(
            isReplacedBy(
                home,
                place(2, { kind: 'mine', label: '집', position: CITY_HALL }),
            ),
        ).toBe(true);
        expect(
            isReplacedBy(home, place(2, { kind: 'mine', label: '회사' })),
        ).toBe(false);
        // 같은 위치라도 즐겨찾기와 내 장소는 따로 둔다.
        expect(isReplacedBy(home, place(2))).toBe(false);
    });
});

describe('placesAt, savedPlaceTitle', () => {
    it('같은 위치의 장소만 고른다', () => {
        const home = place(2, { kind: 'mine', label: '집' });
        const places = [place(1), home, place(3, { position: CITY_HALL })];

        expect(placesAt(places, [...SEOUL_STATION])).toEqual([place(1), home]);
    });

    it('내 장소는 붙인 이름을 보인다', () => {
        expect(savedPlaceTitle(place(1))).toBe('서울역');
        expect(savedPlaceTitle(place(1, { kind: 'mine', label: '집' }))).toBe(
            '집',
        );
    });
});
