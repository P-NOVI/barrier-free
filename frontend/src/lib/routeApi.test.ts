import { afterEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from './apiClient';
import { fetchRoute, type RouteRequest } from './routeApi';

const BASE_URL = 'http://api.test';
const REQUEST: RouteRequest = {
    start: [126.9707, 37.5547],
    goal: [126.9779, 37.5663],
    preset: 'manual_wheelchair',
};

function jsonResponse(body: unknown, status = 200): Response {
    return new Response(JSON.stringify(body), {
        status,
        headers: { 'Content-Type': 'application/json' },
    });
}

afterEach(() => {
    vi.unstubAllGlobals();
});

describe('fetchRoute', () => {
    it('요청을 JSON 으로 POST 하고 응답을 돌려준다', async () => {
        const route = { distance_m: 1616.6, coordinates: [[126.97, 37.55]] };
        const fetchMock = vi.fn().mockResolvedValue(jsonResponse(route));
        vi.stubGlobal('fetch', fetchMock);

        await expect(
            fetchRoute(REQUEST, { baseUrl: BASE_URL }),
        ).resolves.toEqual(route);

        const [url, init] = fetchMock.mock.calls[0];
        expect(String(url)).toBe('http://api.test/api/route');
        expect(init.method).toBe('POST');
        expect(JSON.parse(init.body)).toEqual(REQUEST);
    });

    it('백엔드 detail 의 안내 문구와 reason 을 오류로 바꾼다', async () => {
        vi.stubGlobal(
            'fetch',
            vi.fn().mockResolvedValue(
                jsonResponse(
                    {
                        detail: {
                            reason: 'no_path',
                            message: '이동 조건에 맞는 경로가 없습니다.',
                        },
                    },
                    404,
                ),
            ),
        );

        const error = await fetchRoute(REQUEST, { baseUrl: BASE_URL }).catch(
            (reason: unknown) => reason,
        );
        expect(error).toBeInstanceOf(ApiError);
        expect(error).toMatchObject({
            reason: 'no_path',
            message: '이동 조건에 맞는 경로가 없습니다.',
        });
    });

    it('detail 형식이 다르면 상태 코드를 담은 문구를 쓴다', async () => {
        vi.stubGlobal(
            'fetch',
            vi
                .fn()
                .mockResolvedValue(
                    jsonResponse({ detail: [{ msg: 'invalid' }] }, 422),
                ),
        );

        await expect(
            fetchRoute(REQUEST, { baseUrl: BASE_URL }),
        ).rejects.toMatchObject({ reason: 'http', message: /422/ });
    });

    it('서버에 연결하지 못하면 백엔드 실행을 안내한다', async () => {
        vi.stubGlobal(
            'fetch',
            vi.fn().mockRejectedValue(new TypeError('Failed to fetch')),
        );

        await expect(
            fetchRoute(REQUEST, { baseUrl: BASE_URL }),
        ).rejects.toMatchObject({ reason: 'network' });
    });

    it('주소 설정이 없으면 요청하지 않고 실패한다', async () => {
        const fetchMock = vi.fn();
        vi.stubGlobal('fetch', fetchMock);

        await expect(fetchRoute(REQUEST, { baseUrl: '' })).rejects.toThrow(
            'VITE_API_BASE_URL',
        );
        expect(fetchMock).not.toHaveBeenCalled();
    });
});
