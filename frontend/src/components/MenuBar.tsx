import type { Tab } from '../lib/sheet';

const ITEMS: { tab: Tab; label: string; icon: string }[] = [
    {
        tab: 'search',
        label: '검색',
        icon: 'M10.5 4a6.5 6.5 0 1 0 0 13 6.5 6.5 0 0 0 0-13ZM15.2 15.2 20 20',
    },
    {
        tab: 'route',
        label: '길찾기',
        icon: 'M5 19v-6.5A3.5 3.5 0 0 1 8.5 9H19M15 5l4 4-4 4',
    },
    {
        tab: 'saved',
        label: '저장',
        icon: 'M7 4h10v16l-5-3.5L7 20Z',
    },
    {
        tab: 'my',
        label: 'My',
        icon: 'M12 4.5a4 4 0 1 0 0 8 4 4 0 0 0 0-8ZM4.5 20.5a7.5 7.5 0 0 1 15 0',
    },
];

type MenuBarProps = {
    tab: Tab;
    onSelect: (tab: Tab) => void;
};

/** 메뉴: 검색, 길찾기, 저장, My. 좁은 화면은 화면 아래, 넓은 화면은 왼쪽 패널 위에 둔다. */
export default function MenuBar({ tab, onSelect }: MenuBarProps) {
    return (
        <nav className="menu-bar" aria-label="메뉴">
            {ITEMS.map((item) => (
                <button
                    key={item.tab}
                    type="button"
                    className="menu-bar__item"
                    aria-current={item.tab === tab ? 'page' : undefined}
                    onClick={() => onSelect(item.tab)}
                >
                    <svg viewBox="0 0 24 24" aria-hidden="true">
                        <path d={item.icon} />
                    </svg>
                    {item.label}
                </button>
            ))}
        </nav>
    );
}
