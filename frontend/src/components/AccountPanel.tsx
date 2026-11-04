import { useEffect, useState } from 'react';

import {
    fetchSession,
    loginUrl,
    logout,
    PROVIDER_LABELS,
    type Provider,
    type Session,
} from '../lib/authApi';

const PROVIDERS: Provider[] = ['kakao', 'google'];

type SessionState =
    | { status: 'loading' }
    | { status: 'error' }
    | { status: 'success'; session: Session };

type AccountPanelProps = {
    /** 처음 띄울 알림 (예: 소셜 로그인 실패) */
    initialMessage?: string;
    /** 로그아웃해서 사용자가 바뀌었을 때 */
    onSessionChange: () => void;
};

/**
 * 로그인·로그아웃. 넓은 화면은 오른쪽 위 계정 메뉴, 좁은 화면은 My 탭에 보인다. 로그인하지 않아도 기록·장소는 이 브라우저에 이어지고,
 * 로그인하면 계정으로 옮겨진다.
 */
export default function AccountPanel({
    initialMessage = '',
    onSessionChange,
}: AccountPanelProps) {
    const [state, setState] = useState<SessionState>({ status: 'loading' });
    const [message, setMessage] = useState(initialMessage);

    useEffect(() => {
        let cancelled = false;
        fetchSession()
            .then((session) => {
                if (!cancelled) setState({ status: 'success', session });
            })
            .catch(() => {
                if (!cancelled) setState({ status: 'error' });
            });
        return () => {
            cancelled = true;
        };
    }, []);

    const handleLogout = () => {
        logout()
            .then(() => fetchSession())
            .then((session) => {
                setState({ status: 'success', session });
                setMessage('');
                onSessionChange();
            })
            .catch((error: Error) => setMessage(error.message));
    };

    if (state.status === 'loading') {
        return <p className="account-panel__status">불러오는 중…</p>;
    }
    if (state.status === 'error') {
        return (
            <p className="account-panel__status">
                서버에 연결하지 못해 로그인할 수 없어요. 잠시 뒤 다시 열어
                주세요.
            </p>
        );
    }

    const { providers } = state.session;
    return (
        <div className="account-panel">
            {message && (
                <p role="alert" className="account-panel__error">
                    {message}
                </p>
            )}
            {providers.length > 0 ? (
                <>
                    <p className="account-panel__status">
                        {providers
                            .map((provider) => PROVIDER_LABELS[provider])
                            .join(' · ')}{' '}
                        계정으로 로그인했어요.
                    </p>
                    <button
                        type="button"
                        className="account-panel__button"
                        onClick={handleLogout}
                    >
                        로그아웃
                    </button>
                </>
            ) : (
                <>
                    <p className="account-panel__status">
                        로그인하면 기록과 저장한 장소를 다른 기기에서도 볼 수
                        있어요.
                    </p>
                    {PROVIDERS.map((provider) => (
                        <a
                            key={provider}
                            className={`account-panel__button account-panel__button--${provider}`}
                            href={loginUrl(provider)}
                        >
                            {PROVIDER_LABELS[provider]}로 로그인
                        </a>
                    ))}
                </>
            )}
        </div>
    );
}
