import { afterEach, describe, expect, it, vi } from 'vitest';

import { findAddress, type Place, searchPlaces } from './placeApi';

const BASE_URL = 'http://api.test';
const CITY_HALL: Place = {
    name: '서울특별시청',
    address: '서울 중구 태평로1가 31',
    road_address: '서울 중구 세종대로 110',
    category: '공공기관',
    position: [126.9786, 37.5668],
    distance_m: 120,
};

afterEach(() => {
    vi.unstubAllGlobals();
});

function stubPlaces(places: Place[]) {
    const fetchMock = vi
        .fn()
        .mockResolvedValue(
            new Response(JSON.stringify({ places }), { status: 200 }),
        );
    vi.stubGlobal('fetch', fetchMock);
    return fetchMock;
}

describe('searchPlaces', () => {
    it('검색어로 GET 하고 장소 목록을 돌려준다', async () => {
        const fetchMock = stubPlaces([CITY_HALL]);

        await expect(
            searchPlaces('시청', null, { baseUrl: BASE_URL }),
        ).resolves.toEqual([CITY_HALL]);

        const [url, init] = fetchMock.mock.calls[0];
        expect(String(url)).toBe(
            'http://api.test/api/places/search?query=%EC%8B%9C%EC%B2%AD',
        );
        expect(init.method).toBeUndefined();
    });

    it('기준 좌표를 lng·lat 으로 보낸다', async () => {
        const fetchMock = stubPlaces([]);

        await searchPlaces('편의점', [126.9779, 37.5663], {
            baseUrl: BASE_URL,
        });

        const url = new URL(String(fetchMock.mock.calls[0][0]));
        expect(url.searchParams.get('lng')).toBe('126.9779');
        expect(url.searchParams.get('lat')).toBe('37.5663');
    });

    it('검색 키가 없다는 백엔드 안내를 그대로 쓴다', async () => {
        vi.stubGlobal(
            'fetch',
            vi.fn().mockResolvedValue(
                new Response(
                    JSON.stringify({
                        detail: {
                            reason: 'search_unavailable',
                            message: '장소 검색 키가 없습니다.',
                        },
                    }),
                    { status: 503 },
                ),
            ),
        );

        await expect(
            searchPlaces('시청', null, { baseUrl: BASE_URL }),
        ).rejects.toMatchObject({
            reason: 'search_unavailable',
            message: '장소 검색 키가 없습니다.',
        });
    });
});

describe('findAddress', () => {
    it('좌표를 lng·lat 으로 보내고 주소를 돌려준다', async () => {
        const address = {
            name: '서울특별시청',
            building_name: '서울특별시청',
            road_address: '서울특별시 중구 세종대로 110',
            address: '서울 중구 태평로1가 31',
        };
        const fetchMock = vi
            .fn()
            .mockResolvedValue(
                new Response(JSON.stringify({ address }), { status: 200 }),
            );
        vi.stubGlobal('fetch', fetchMock);

        await expect(
            findAddress([126.9779, 37.5663], { baseUrl: BASE_URL }),
        ).resolves.toEqual(address);

        const url = new URL(String(fetchMock.mock.calls[0][0]));
        expect(url.pathname).toBe('/api/places/address');
        expect(url.searchParams.get('lng')).toBe('126.9779');
        expect(url.searchParams.get('lat')).toBe('37.5663');
    });

    it('주소가 없는 곳이면 null', async () => {
        vi.stubGlobal(
            'fetch',
            vi.fn().mockResolvedValue(
                new Response(JSON.stringify({ address: null }), {
                    status: 200,
                }),
            ),
        );

        await expect(
            findAddress([126.5, 37.0], { baseUrl: BASE_URL }),
        ).resolves.toBeNull();
    });
});
