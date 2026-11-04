import { useEffect, useRef } from 'react';

import AccountPanel from './AccountPanel';

type AccountMenuProps = {
    /** 처음 띄울 알림 (예: 소셜 로그인 실패). 있으면 메뉴를 펼친 채로 시작한다. */
    initialMessage?: string;
    /** 로그아웃해서 사용자가 바뀌었을 때 */
    onSessionChange: () => void;
};

/** 넓은 화면 오른쪽 위 계정 아이콘. 누르면 로그인·로그아웃을 펼친다. */
export default function AccountMenu({
    initialMessage,
    onSessionChange,
}: AccountMenuProps) {
    const menuRef = useRef<HTMLDetailsElement>(null);

    // 메뉴 밖을 누르면 닫는다.
    useEffect(() => {
        const closeOutside = (event: PointerEvent) => {
            const menu = menuRef.current;
            if (
                menu?.open &&
                event.target instanceof Node &&
                !menu.contains(event.target)
            ) {
                menu.open = false;
            }
        };
        document.addEventListener('pointerdown', closeOutside);
        return () => document.removeEventListener('pointerdown', closeOutside);
    }, []);

    return (
        <details
            ref={menuRef}
            className="account-menu"
            open={initialMessage ? true : undefined}
            onKeyDown={(event) => {
                if (event.key === 'Escape' && menuRef.current?.open) {
                    menuRef.current.open = false;
                    menuRef.current.querySelector('summary')?.focus();
                }
            }}
        >
            <summary className="account-menu__toggle" aria-label="내 계정">
                <svg viewBox="0 0 24 24" aria-hidden="true">
                    <circle cx="12" cy="8.5" r="4" />
                    <path d="M4.5 20.5a7.5 7.5 0 0 1 15 0" />
                </svg>
            </summary>
            <div className="account-menu__panel">
                <AccountPanel
                    initialMessage={initialMessage}
                    onSessionChange={onSessionChange}
                />
            </div>
        </details>
    );
}
