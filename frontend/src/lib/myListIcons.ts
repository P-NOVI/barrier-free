// My 탭 목록 아이콘(24×24 선)
export const MY_LIST_ICONS = {
    star: 'M12 4l2.4 5 5.4.6-4 3.7 1.1 5.3L12 16l-4.9 2.6 1.1-5.3-4-3.7 5.4-.6Z',
    home: 'M4 11 12 4l8 7v9h-5v-6H9v6H4Z',
    work: 'M6 20V5h9v15M15 9h3v11M9 8h2M9 11h2M9 14h2',
    pin: 'M12 21s-6-5.5-6-10a6 6 0 0 1 12 0c0 4.5-6 10-6 10ZM12 13a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z',
    add: 'M12 6v12M6 12h12',
    flag: 'M6 21V4M6 5h11l-2 3.5 2 3.5H6',
    route: 'M6 19a2 2 0 1 0 0-4 2 2 0 0 0 0 4ZM18 9a2 2 0 1 0 0-4 2 2 0 0 0 0 4ZM6 15V10a4 4 0 0 1 4-4h6M18 9v5a4 4 0 0 1-4 4H8',
};

/**
 * My 탭 내 장소에 늘 보이는 칸. 길찾기 입력칸 아래 버튼도 같은 칸을 쓴다.
 * label 은 장소 카드 북마크의 이름(MY_PLACE_LABELS)과 같다.
 */
export const MY_PLACE_SLOTS = [
    { label: '집', title: '집', icon: MY_LIST_ICONS.home },
    { label: '회사', title: '회사/학교', icon: MY_LIST_ICONS.work },
];
