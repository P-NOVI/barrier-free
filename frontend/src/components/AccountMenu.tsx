import { useEffect, useState } from 'react';

import {
    fetchSession,
    loginUrl,
    logout,
    PROVIDER_LABELS,
    type Provider,
    type Session,
    takeLoginFailure,
} from '../lib/authApi';

const PROVIDERS: Provider[] = ['kakao', 'google'];

/**
 * 지도 위 '로그인' 메뉴. 로그인하지 않아도 검색·경로 이력은 이 브라우저에 이어지고,
 * 로그인하면 그 이력이 계정으로 옮겨진다. 백엔드(DB)가 없으면 메뉴를 숨긴다.
 */
export default function AccountMenu() {
    const [session, setSession] = useState<Session | null>(null);
    const [message, setMessage] = useState(() =>
        takeLoginFailure() ? '로그인하지 못했어요. 다시 시도해 주세요.' : '',
    );

    useEffect(() => {
        let cancelled = false;
        fetchSession()
            .then((found) => {
                if (!cancelled) setSession(found);
            })
            .catch(() => {
                if (!cancelled) setSession(null);
            });
        return () => {
            cancelled = true;
        };
    }, []);

    if (!session) {
        return null;
    }

    const handleLogout = () => {
        logout()
            .then(() => fetchSession())
            .then((found) => {
                setSession(found);
                setMessage('');
            })
            .catch((error: Error) => setMessage(error.message));
    };

    const signedIn = session.providers.length > 0;
    return (
        <details className="account-menu" open={message !== '' || undefined}>
            <summary className="account-menu__toggle">
                {signedIn ? '내 계정' : '로그인'}
            </summary>
            <div className="account-menu__panel">
                {message && (
                    <p role="alert" className="account-menu__message">
                        {message}
                    </p>
                )}
                {signedIn ? (
                    <>
                        <p className="account-menu__status">
                            {session.providers
                                .map((provider) => PROVIDER_LABELS[provider])
                                .join(' · ')}{' '}
                            계정으로 로그인했어요.
                        </p>
                        <button
                            type="button"
                            className="account-menu__logout"
                            onClick={handleLogout}
                        >
                            로그아웃
                        </button>
                    </>
                ) : (
                    <>
                        <p className="account-menu__status">
                            로그인하면 검색·경로 기록을 다른 기기에서도 볼 수
                            있어요.
                        </p>
                        {PROVIDERS.map((provider) => (
                            <a
                                key={provider}
                                className={`account-menu__login account-menu__login--${provider}`}
                                href={loginUrl(provider)}
                            >
                                {PROVIDER_LABELS[provider]}로 로그인
                            </a>
                        ))}
                    </>
                )}
            </div>
        </details>
    );
}
