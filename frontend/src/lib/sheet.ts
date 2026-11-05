// 아래 메뉴를 눌러 여는 시트. 제목만 보이게 접거나, 화면 절반, 끝까지(전체) 펼친다.

export type SheetSnap = 'collapsed' | 'half' | 'full';

/** 아래 메뉴 탭. 검색은 시트를 닫고 지도와 위 검색창만 보인다. */
export type Tab = 'search' | 'route' | 'my';

/** 단계마다 화면에 보이는 시트 높이(px) */
export type SnapHeights = Record<SheetSnap, number>;

const SNAPS: SheetSnap[] = ['collapsed', 'half', 'full'];

// 이보다 적게 움직이면 끌기가 아니라 누른 것으로 본다(px).
export const TAP_SLOP_PX = 6;
// 이보다 빠르게 놓으면(px/ms) 튕긴 쪽의 다음 단계로 간다.
export const FLICK_SPEED = 0.4;
// 가장 낮은·높은 단계를 넘겨 끌면 이 비율만큼만 따라온다.
export const RUBBER_BAND = 0.25;

/** 끄는 중 보이는 높이. start 에서 dy(아래가 +)만큼 끈 위치 */
export function dragHeight(
    start: number,
    dy: number,
    heights: SnapHeights,
): number {
    const height = start - dy;
    if (height > heights.full) {
        return heights.full + (height - heights.full) * RUBBER_BAND;
    }
    if (height < heights.collapsed) {
        return heights.collapsed - (heights.collapsed - height) * RUBBER_BAND;
    }
    return height;
}

/**
 * 손을 뗐을 때 멈출 단계. velocity 는 위로 올리는 쪽이 +(px/ms).
 * 빠르게 튕기면 그 쪽의 다음 단계, 천천히 놓으면 가장 가까운 단계로 간다.
 */
export function snapAfterRelease(
    height: number,
    velocity: number,
    heights: SnapHeights,
): SheetSnap {
    if (velocity >= FLICK_SPEED) {
        return SNAPS.find((snap) => heights[snap] > height + 1) ?? 'full';
    }
    if (velocity <= -FLICK_SPEED) {
        return (
            [...SNAPS].reverse().find((snap) => heights[snap] < height - 1) ??
            'collapsed'
        );
    }
    return SNAPS.reduce((best, snap) =>
        Math.abs(heights[snap] - height) < Math.abs(heights[best] - height)
            ? snap
            : best,
    );
}

/** 손잡이를 눌렀을 때: 접혀 있으면 절반으로 펴고, 펼쳐 있으면 한 단계 내린다. */
export function toggleSnap(snap: SheetSnap): SheetSnap {
    return snap === 'half' ? 'collapsed' : 'half';
}

/**
 * 메뉴를 눌렀을 때 다음 탭·단계. 다른 탭이면 절반으로 열고,
 * 열려 있는 탭을 다시 누르면 접거나 절반으로 편다.
 */
export function selectTab(
    current: { tab: Tab; snap: SheetSnap },
    next: Tab,
): { tab: Tab; snap: SheetSnap } {
    if (next !== current.tab || next === 'search') {
        return { tab: next, snap: 'half' };
    }
    return {
        tab: next,
        snap: current.snap === 'collapsed' ? 'half' : 'collapsed',
    };
}
