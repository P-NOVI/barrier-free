import { afterEach, describe, expect, it, vi } from 'vitest';

import {
    addSavedRoute,
    deleteSavedRoute,
    fetchSavedRoutes,
    findSavedRoute,
    isSameRoute,
    type SavedRoute,
} from './savedRoutesApi';

const BASE_URL = 'http://api.test';
const OPTIONS = { baseUrl: BASE_URL };
const SEOUL_STATION: [number, number] = [126.9707, 37.5547];
const CITY_HALL: [number, number] = [126.9779, 37.5663];

function savedRoute(
    id: number,
    overrides: Partial<SavedRoute> = {},
): SavedRoute {
    return {
        id,
        start_name: '서울역',
        start: SEOUL_STATION,
        goal_name: '서울시청',
        goal: CITY_HALL,
        preset: 'manual_wheelchair',
        distance_m: 1520,
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

describe('내 경로 API', () => {
    it('쿠키와 함께 내 경로를 받는다', async () => {
        const fetchMock = vi
            .fn()
            .mockResolvedValue(jsonResponse({ routes: [savedRoute(1)] }));
        vi.stubGlobal('fetch', fetchMock);

        await expect(fetchSavedRoutes(OPTIONS)).resolves.toEqual([
            savedRoute(1),
        ]);

        const [url, init] = fetchMock.mock.calls[0];
        expect(String(url)).toBe('http://api.test/api/me/saved-routes');
        expect(init.credentials).toBe('include');
    });

    it('경로를 POST 하고 DELETE 한다', async () => {
        const fetchMock = vi
            .fn()
            .mockResolvedValueOnce(jsonResponse(savedRoute(1), 201))
            .mockResolvedValueOnce(new Response(null, { status: 204 }));
        vi.stubGlobal('fetch', fetchMock);
        const entry = {
            start_name: '서울역',
            start: SEOUL_STATION,
            goal_name: '서울시청',
            goal: CITY_HALL,
            preset: 'manual_wheelchair' as const,
            distance_m: 1520,
        };

        await expect(addSavedRoute(entry, OPTIONS)).resolves.toEqual(
            savedRoute(1),
        );
        await deleteSavedRoute(1, OPTIONS);

        const [postUrl, postInit] = fetchMock.mock.calls[0];
        expect(String(postUrl)).toBe('http://api.test/api/me/saved-routes');
        expect(postInit.method).toBe('POST');
        expect(JSON.parse(postInit.body)).toEqual(entry);
        const [deleteUrl, deleteInit] = fetchMock.mock.calls[1];
        expect(String(deleteUrl)).toBe('http://api.test/api/me/saved-routes/1');
        expect(deleteInit.method).toBe('DELETE');
    });
});

describe('isSameRoute', () => {
    it('출발·도착 위치와 이동 조건이 같으면 같은 경로다', () => {
        expect(
            isSameRoute(savedRoute(1), savedRoute(2, { goal_name: '시청' })),
        ).toBe(true);
        expect(
            isSameRoute(savedRoute(1), savedRoute(2, { preset: 'general' })),
        ).toBe(false);
        expect(
            isSameRoute(savedRoute(1), savedRoute(2, { goal: SEOUL_STATION })),
        ).toBe(false);
    });
});

describe('findSavedRoute', () => {
    it('지금 경로와 같은 내 경로를 찾는다', () => {
        const routes = [savedRoute(1, { preset: 'general' }), savedRoute(2)];

        expect(findSavedRoute(routes, savedRoute(9))?.id).toBe(2);
        expect(findSavedRoute(routes, null)).toBeNull();
        expect(
            findSavedRoute(routes, savedRoute(9, { preset: 'stroller' })),
        ).toBeNull();
    });
});
