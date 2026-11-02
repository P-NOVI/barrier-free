import { afterEach, describe, expect, it, vi } from 'vitest';

import {
    addRoute,
    addSearch,
    deleteSearch,
    fetchRoutes,
    fetchSearches,
    recentPlaces,
    type RouteHistory,
    routeEndpoints,
    type SearchHistory,
    searchEndpoint,
    toRouteEntry,
    toSearchEntry,
} from './historyApi';
import type { Place } from './placeApi';

const BASE_URL = 'http://api.test';
const OPTIONS = { baseUrl: BASE_URL };
const SEOUL_STATION: [number, number] = [126.9707, 37.5547];
const CITY_HALL: [number, number] = [126.9779, 37.5663];

const PLACE: Place = {
    name: '서울역',
    address: '서울 용산구 동자동 43-205',
    road_address: '서울 용산구 한강대로 405',
    category: '교통',
    position: SEOUL_STATION,
    distance_m: null,
};

function search(id: number, overrides: Partial<SearchHistory> = {}) {
    return {
        id,
        query: '서울',
        place_name: '서울역',
        address: null,
        position: SEOUL_STATION,
        created_at: '2026-11-02T00:00:00',
        ...overrides,
    };
}

const ROUTE: RouteHistory = {
    id: 1,
    start_name: '서울역',
    start: SEOUL_STATION,
    goal_name: '서울시청',
    goal: CITY_HALL,
    preset: 'stroller',
    distance_m: 1616.6,
    created_at: '2026-11-02T00:00:00',
};

function jsonResponse(body: unknown, status = 200): Response {
    return new Response(JSON.stringify(body), { status });
}

afterEach(() => {
    vi.unstubAllGlobals();
});

describe('이력 API', () => {
    it('쿠키와 함께 최근 검색을 받는다', async () => {
        const fetchMock = vi
            .fn()
            .mockResolvedValue(jsonResponse({ searches: [search(1)] }));
        vi.stubGlobal('fetch', fetchMock);

        await expect(fetchSearches(OPTIONS)).resolves.toEqual([search(1)]);

        const [url, init] = fetchMock.mock.calls[0];
        expect(String(url)).toBe('http://api.test/api/me/searches');
        expect(init.method).toBeUndefined();
        expect(init.credentials).toBe('include');
    });

    it('검색 기록을 POST 한다', async () => {
        const fetchMock = vi.fn().mockResolvedValue(jsonResponse(search(1)));
        vi.stubGlobal('fetch', fetchMock);
        const entry = toSearchEntry('서울', PLACE);

        await addSearch(entry, OPTIONS);

        const [url, init] = fetchMock.mock.calls[0];
        expect(String(url)).toBe('http://api.test/api/me/searches');
        expect(init.method).toBe('POST');
        expect(JSON.parse(init.body)).toEqual(entry);
    });

    it('검색 기록 하나를 DELETE 한다', async () => {
        const fetchMock = vi
            .fn()
            .mockResolvedValue(new Response(null, { status: 204 }));
        vi.stubGlobal('fetch', fetchMock);

        await expect(deleteSearch(7, OPTIONS)).resolves.toBeUndefined();

        const [url, init] = fetchMock.mock.calls[0];
        expect(String(url)).toBe('http://api.test/api/me/searches/7');
        expect(init.method).toBe('DELETE');
    });

    it('최근 경로를 받고 경로 기록을 POST 한다', async () => {
        const fetchMock = vi
            .fn()
            .mockResolvedValueOnce(jsonResponse({ routes: [ROUTE] }))
            .mockResolvedValueOnce(jsonResponse(ROUTE));
        vi.stubGlobal('fetch', fetchMock);

        await expect(fetchRoutes(OPTIONS)).resolves.toEqual([ROUTE]);
        await addRoute(
            {
                start_name: '서울역',
                start: SEOUL_STATION,
                goal_name: '서울시청',
                goal: CITY_HALL,
                preset: 'stroller',
                distance_m: 1616.6,
            },
            OPTIONS,
        );

        expect(String(fetchMock.mock.calls[0][0])).toBe(
            'http://api.test/api/me/routes',
        );
        const [url, init] = fetchMock.mock.calls[1];
        expect(String(url)).toBe('http://api.test/api/me/routes');
        expect(init.method).toBe('POST');
    });

    it('저장은 앞 저장의 응답(게스트 쿠키)을 받은 뒤에 보낸다', async () => {
        let answerFirst: (response: Response) => void = () => {};
        const fetchMock = vi
            .fn()
            .mockReturnValueOnce(
                new Promise<Response>((resolve) => {
                    answerFirst = resolve;
                }),
            )
            .mockResolvedValue(jsonResponse(ROUTE));
        vi.stubGlobal('fetch', fetchMock);

        const first = addSearch(toSearchEntry('서울', PLACE), OPTIONS);
        const second = addRoute(
            toRouteEntry(
                {
                    start: { position: SEOUL_STATION, label: '서울역' },
                    goal: { position: CITY_HALL, label: '서울시청' },
                },
                'general',
                100,
            )!,
            OPTIONS,
        );
        await Promise.resolve();
        expect(fetchMock).toHaveBeenCalledTimes(1);

        answerFirst(jsonResponse(search(1)));
        await Promise.all([first, second]);
        expect(fetchMock).toHaveBeenCalledTimes(2);
    });

    it('앞 저장이 실패해도 다음 저장은 보낸다', async () => {
        const fetchMock = vi
            .fn()
            .mockRejectedValueOnce(new TypeError('Failed to fetch'))
            .mockResolvedValue(jsonResponse(search(2)));
        vi.stubGlobal('fetch', fetchMock);

        await expect(
            addSearch(toSearchEntry('서울', PLACE), OPTIONS),
        ).rejects.toThrow();
        await expect(
            addSearch(toSearchEntry('시청', PLACE), OPTIONS),
        ).resolves.toEqual(search(2));
    });
});

describe('toSearchEntry', () => {
    it('도로명 주소를 먼저 쓴다', () => {
        expect(toSearchEntry(' 서울 ', PLACE)).toEqual({
            query: '서울',
            place_name: '서울역',
            address: '서울 용산구 한강대로 405',
            position: SEOUL_STATION,
        });
    });

    it('검색어가 비면 장소 이름, 길면 백엔드 한도까지 자른다', () => {
        const place = { ...PLACE, road_address: '' };

        expect(toSearchEntry('  ', place).query).toBe('서울역');
        expect(toSearchEntry('가'.repeat(150), place).query).toHaveLength(100);
        expect(toSearchEntry('서울', place).address).toBe(PLACE.address);
    });
});

describe('searchEndpoint', () => {
    it('고른 장소의 이름과 위치', () => {
        expect(searchEndpoint(search(1))).toEqual({
            position: SEOUL_STATION,
            label: '서울역',
        });
    });

    it('장소를 고르지 않은 기록은 null', () => {
        expect(searchEndpoint(search(1, { position: null }))).toBeNull();
    });
});

describe('recentPlaces', () => {
    it('같은 장소는 최근 것 하나만, limit 개까지', () => {
        const searches = [
            search(3, { query: '서울역' }),
            search(2, { position: null }),
            search(1, { query: '서울' }),
            search(4, { place_name: '서울시청', position: CITY_HALL }),
        ];

        expect(recentPlaces(searches, 5).map((entry) => entry.id)).toEqual([
            3, 4,
        ]);
        expect(recentPlaces(searches, 1).map((entry) => entry.id)).toEqual([3]);
    });
});

describe('toRouteEntry', () => {
    it('출발·도착 이름과 위치, 프리셋, 거리', () => {
        expect(
            toRouteEntry(
                {
                    start: { position: SEOUL_STATION, label: '서울역' },
                    goal: { position: CITY_HALL, label: '서울시청' },
                },
                'stroller',
                1616.6,
            ),
        ).toEqual({
            start_name: '서울역',
            start: SEOUL_STATION,
            goal_name: '서울시청',
            goal: CITY_HALL,
            preset: 'stroller',
            distance_m: 1616.6,
        });
    });

    it('도착지가 없으면 null', () => {
        expect(
            toRouteEntry(
                {
                    start: { position: SEOUL_STATION, label: '서울역' },
                    goal: null,
                },
                'general',
                0,
            ),
        ).toBeNull();
    });
});

describe('routeEndpoints', () => {
    it('기록의 출발·도착', () => {
        expect(routeEndpoints(ROUTE)).toEqual({
            start: { position: SEOUL_STATION, label: '서울역' },
            goal: { position: CITY_HALL, label: '서울시청' },
        });
    });

    it('현재 위치에서 출발한 기록은 출발지를 다시 쓰지 않는다', () => {
        expect(
            routeEndpoints({ ...ROUTE, start_name: '현재 위치' }).start,
        ).toBeNull();
    });
});
