import { afterEach, describe, expect, it, vi } from 'vitest';

import { fetchSession, loginUrl, logout, takeLoginFailure } from './authApi';

const BASE_URL = 'http://api.test';

afterEach(() => {
    vi.unstubAllGlobals();
});

function fakeLocation(href: string) {
    const replaceState = vi.fn();
    return {
        location: { href } as Location,
        history: { state: null, replaceState } as unknown as History,
        replaceState,
    };
}

describe('fetchSession', () => {
    it('쿠키와 함께 GET /api/session 을 부른다', async () => {
        const session = {
            is_guest: false,
            providers: ['kakao'],
            preset: 'general',
            is_admin: false,
        };
        const fetchMock = vi
            .fn()
            .mockResolvedValue(new Response(JSON.stringify(session)));
        vi.stubGlobal('fetch', fetchMock);

        await expect(fetchSession({ baseUrl: BASE_URL })).resolves.toEqual(
            session,
        );

        const [url, init] = fetchMock.mock.calls[0];
        expect(String(url)).toBe('http://api.test/api/session');
        expect(init.method).toBeUndefined();
        expect(init.credentials).toBe('include');
    });
});

describe('logout', () => {
    it('본문 없이 POST 하고 204 응답을 받아들인다', async () => {
        const fetchMock = vi
            .fn()
            .mockResolvedValue(new Response(null, { status: 204 }));
        vi.stubGlobal('fetch', fetchMock);

        await expect(logout({ baseUrl: BASE_URL })).resolves.toBeUndefined();

        const [url, init] = fetchMock.mock.calls[0];
        expect(String(url)).toBe('http://api.test/api/auth/logout');
        expect(init.method).toBe('POST');
        expect(init.body).toBeUndefined();
    });
});

describe('loginUrl', () => {
    it('백엔드 로그인 시작 주소', () => {
        expect(loginUrl('google', BASE_URL)).toBe(
            'http://api.test/api/auth/google/login',
        );
    });

    it('주소 설정이 비어 있으면 화면과 같은 주소', () => {
        vi.stubGlobal('location', { origin: 'http://localhost:5173' });

        expect(loginUrl('kakao', '')).toBe(
            'http://localhost:5173/api/auth/kakao/login',
        );
    });
});

describe('takeLoginFailure', () => {
    it('?login=failed 면 true 를 주고 주소에서 지운다', () => {
        const { location, history, replaceState } = fakeLocation(
            'http://localhost:5173/?login=failed&x=1',
        );

        expect(takeLoginFailure(location, history)).toBe(true);
        expect(String(replaceState.mock.calls[0][2])).toBe(
            'http://localhost:5173/?x=1',
        );
    });

    it('실패 표시가 없으면 주소를 그대로 둔다', () => {
        const { location, history, replaceState } = fakeLocation(
            'http://localhost:5173/',
        );

        expect(takeLoginFailure(location, history)).toBe(false);
        expect(replaceState).not.toHaveBeenCalled();
    });
});
