// 로그인 상태와 카카오·구글 로그인. 응답 형식은 backend/app/schemas.py 의 SessionResponse 와 같다.

import { type ApiOptions, apiUrl, requestJson } from './apiClient';

export type Provider = 'kakao' | 'google';

export const PROVIDER_LABELS: Record<Provider, string> = {
    kakao: '카카오',
    google: '구글',
};

export type Session = {
    /** 카카오·구글 계정이 연결되지 않았으면 true */
    is_guest: boolean;
    providers: Provider[];
    preset: string;
    /** 관리자 계정이면 true. 관리자 화면(/admin)을 열 수 있다. */
    is_admin: boolean;
};

/** 쿠키의 사용자. 쿠키가 없어도 게스트를 만들지 않는다. */
export function fetchSession(options?: ApiOptions): Promise<Session> {
    return requestJson<Session>(
        {
            path: '/api/session',
            failureMessage: '로그인 상태를 확인하지 못했습니다.',
        },
        options,
    );
}

export function logout(options?: ApiOptions): Promise<void> {
    return requestJson<void>(
        {
            path: '/api/auth/logout',
            method: 'POST',
            failureMessage: '로그아웃하지 못했습니다.',
        },
        options,
    );
}

/** 이 주소로 이동하면 카카오·구글 로그인 화면으로 넘어간다. */
export function loginUrl(provider: Provider, baseUrl?: string): string {
    return apiUrl(`/api/auth/${provider}/login`, baseUrl);
}

/**
 * 로그인에 실패하면 백엔드가 ?login=failed 를 붙여 돌려보낸다.
 * 실패였는지 알려 주고, 새로고침해도 다시 뜨지 않게 주소에서 지운다.
 */
export function takeLoginFailure(
    location: Location = window.location,
    history: History = window.history,
): boolean {
    const url = new URL(location.href);
    if (url.searchParams.get('login') !== 'failed') {
        return false;
    }
    url.searchParams.delete('login');
    history.replaceState(history.state, '', url);
    return true;
}
