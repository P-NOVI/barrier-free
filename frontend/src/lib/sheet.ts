// 아래 메뉴를 눌러 여는 시트. 화면 절반까지 펼치거나 제목만 보이게 접는다.

export type SheetSnap = 'half' | 'collapsed';

/** 아래 메뉴 탭. 검색은 시트를 닫고 지도와 위 검색창만 보인다. */
export type Tab = 'search' | 'route' | 'my';

// 이보다 적게 움직이면 끌기가 아니라 누른 것으로 본다(px).
export const TAP_SLOP_PX = 6;
// 이만큼 넘게 끌어야 다른 단계로 넘어간다(px).
export const SNAP_THRESHOLD_PX = 60;

/** 끈 거리(아래가 +)를 지금 단계에서 갈 수 있는 쪽으로만 둔다. */
export function clampDrag(snap: SheetSnap, dy: number, range: number): number {
    return snap === 'half'
        ? Math.min(Math.max(dy, 0), range)
        : Math.max(Math.min(dy, 0), -range);
}

/** 손을 뗐을 때 단계. 조금만 움직였으면 누른 것으로 보고 단계를 바꾼다. */
export function snapAfterDrag(snap: SheetSnap, dy: number): SheetSnap {
    if (Math.abs(dy) < TAP_SLOP_PX) {
        return toggleSnap(snap);
    }
    if (snap === 'half' && dy > SNAP_THRESHOLD_PX) {
        return 'collapsed';
    }
    if (snap === 'collapsed' && dy < -SNAP_THRESHOLD_PX) {
        return 'half';
    }
    return snap;
}

export function toggleSnap(snap: SheetSnap): SheetSnap {
    return snap === 'half' ? 'collapsed' : 'half';
}

/**
 * 메뉴를 눌렀을 때 다음 탭·단계. 다른 탭이면 절반으로 열고,
 * 열려 있는 탭을 다시 누르면 접거나 편다.
 */
export function selectTab(
    current: { tab: Tab; snap: SheetSnap },
    next: Tab,
): { tab: Tab; snap: SheetSnap } {
    if (next !== current.tab || next === 'search') {
        return { tab: next, snap: 'half' };
    }
    return { tab: next, snap: toggleSnap(current.snap) };
}
