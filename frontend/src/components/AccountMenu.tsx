import { useEffect, useRef, useState } from 'react';

import {
    fetchSession,
    loginUrl,
    logout,
    PROVIDER_LABELS,
    type Provider,
    type Session,
    takeLoginFailure,
} from '../lib/authApi';
import { type SavedPlace, savedPlaceTitle } from '../lib/savedPlacesApi';

const PROVIDERS: Provider[] = ['kakao', 'google'];

type AccountMenuProps = {
    places: SavedPlace[];
    /** 장소 저장·삭제에 실패했을 때 알림 */
    placeError: string | null;
    onSelectPlace: (place: SavedPlace) => void;
    onDeletePlace: (id: number) => void;
    /** 로그아웃해서 사용자가 바뀌었을 때 */
    onSessionChange: () => void;
};

/**
 * 지도 위 동그란 프로필 버튼. 누르면 내 프로필(로그인, 내 장소, 즐겨찾기)을 펼친다.
 * 로그인하지 않아도 이력·장소는 이 브라우저에 이어지고, 로그인하면 계정으로 옮겨진다.
 * 백엔드(DB)가 없으면 메뉴를 숨긴다.
 */
export default function AccountMenu({
    places,
    placeError,
    onSelectPlace,
    onDeletePlace,
    onSessionChange,
}: AccountMenuProps) {
    const menuRef = useRef<HTMLDetailsElement>(null);
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
                onSessionChange();
            })
            .catch((error: Error) => setMessage(error.message));
    };

    const selectPlace = (place: SavedPlace) => {
        if (menuRef.current) {
            menuRef.current.open = false;
        }
        onSelectPlace(place);
    };

    const signedIn = session.providers.length > 0;
    const notice = message || placeError;
    return (
        <details
            ref={menuRef}
            className="account-menu"
            open={message !== '' || undefined}
        >
            <summary className="account-menu__toggle" aria-label="내 프로필">
                <svg
                    className="account-menu__icon"
                    viewBox="0 0 24 24"
                    aria-hidden="true"
                >
                    <circle cx="12" cy="8.5" r="4" />
                    <path d="M4.5 20.5a7.5 7.5 0 0 1 15 0" />
                </svg>
            </summary>
            <div className="account-menu__panel">
                <h2 className="account-menu__title">내 프로필</h2>
                {notice && (
                    <p role="alert" className="account-menu__message">
                        {notice}
                    </p>
                )}
                {signedIn ? (
                    <div className="account-menu__account">
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
                    </div>
                ) : (
                    <>
                        <p className="account-menu__status">
                            로그인하면 기록과 저장한 장소를 다른 기기에서도 볼
                            수 있어요.
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
                <PlaceList
                    title="내 장소"
                    empty="장소 카드에서 '내 장소로 저장'을 눌러 집·회사를 추가해 보세요."
                    places={places.filter((place) => place.kind === 'mine')}
                    onSelect={selectPlace}
                    onDelete={onDeletePlace}
                />
                <PlaceList
                    title="즐겨찾기"
                    empty="장소 카드에서 ☆ 즐겨찾기를 눌러 추가해 보세요."
                    places={places.filter((place) => place.kind === 'favorite')}
                    onSelect={selectPlace}
                    onDelete={onDeletePlace}
                />
            </div>
        </details>
    );
}

type PlaceListProps = {
    title: string;
    empty: string;
    places: SavedPlace[];
    onSelect: (place: SavedPlace) => void;
    onDelete: (id: number) => void;
};

function PlaceList({
    title,
    empty,
    places,
    onSelect,
    onDelete,
}: PlaceListProps) {
    return (
        <section className="account-menu__places" aria-label={title}>
            <h3 className="account-menu__places-title">{title}</h3>
            {places.length === 0 ? (
                <p className="account-menu__status">{empty}</p>
            ) : (
                <ul className="account-menu__place-list">
                    {places.map((place) => (
                        <li key={place.id} className="account-menu__place">
                            <button
                                type="button"
                                className="account-menu__place-pick"
                                onClick={() => onSelect(place)}
                            >
                                <span className="account-menu__place-name">
                                    {savedPlaceTitle(place)}
                                </span>
                                <span className="account-menu__place-detail">
                                    {place.label
                                        ? place.name
                                        : (place.address ?? '')}
                                </span>
                            </button>
                            <button
                                type="button"
                                className="account-menu__place-delete"
                                aria-label={`${savedPlaceTitle(place)} 지우기`}
                                onClick={() => onDelete(place.id)}
                            >
                                ×
                            </button>
                        </li>
                    ))}
                </ul>
            )}
        </section>
    );
}
