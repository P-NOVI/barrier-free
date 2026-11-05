import { describe, expect, it } from 'vitest';

import {
    dragHeight,
    FLICK_SPEED,
    RUBBER_BAND,
    selectTab,
    snapAfterRelease,
    toggleSnap,
} from './sheet';

const HEIGHTS = { collapsed: 140, half: 400, full: 780 };

describe('dragHeight', () => {
    it('단계 사이에서는 끈 만큼 따라온다', () => {
        expect(dragHeight(400, -100, HEIGHTS)).toBe(500);
        expect(dragHeight(400, 100, HEIGHTS)).toBe(300);
    });

    it('맨 위·맨 아래를 넘기면 조금만 따라온다', () => {
        expect(dragHeight(780, -100, HEIGHTS)).toBe(780 + 100 * RUBBER_BAND);
        expect(dragHeight(140, 100, HEIGHTS)).toBe(140 - 100 * RUBBER_BAND);
    });
});

describe('snapAfterRelease', () => {
    it('천천히 놓으면 가장 가까운 단계로 간다', () => {
        expect(snapAfterRelease(250, 0, HEIGHTS)).toBe('collapsed');
        expect(snapAfterRelease(300, 0, HEIGHTS)).toBe('half');
        expect(snapAfterRelease(650, 0, HEIGHTS)).toBe('full');
    });

    it('빠르게 튕기면 그 쪽의 다음 단계로 간다', () => {
        expect(snapAfterRelease(420, FLICK_SPEED, HEIGHTS)).toBe('full');
        expect(snapAfterRelease(380, -FLICK_SPEED, HEIGHTS)).toBe('collapsed');
        expect(snapAfterRelease(160, FLICK_SPEED, HEIGHTS)).toBe('half');
    });

    it('끝 단계 너머로 튕기면 끝 단계에 멈춘다', () => {
        expect(snapAfterRelease(800, FLICK_SPEED * 2, HEIGHTS)).toBe('full');
        expect(snapAfterRelease(120, -FLICK_SPEED * 2, HEIGHTS)).toBe(
            'collapsed',
        );
    });
});

describe('toggleSnap', () => {
    it('접힌 시트는 절반으로 펴고, 펼친 시트는 한 단계 내린다', () => {
        expect(toggleSnap('collapsed')).toBe('half');
        expect(toggleSnap('half')).toBe('collapsed');
        expect(toggleSnap('full')).toBe('half');
    });
});

describe('selectTab', () => {
    it('다른 탭을 누르면 절반으로 연다', () => {
        expect(selectTab({ tab: 'route', snap: 'full' }, 'my')).toEqual({
            tab: 'my',
            snap: 'half',
        });
    });

    it('열린 탭을 다시 누르면 접거나 절반으로 편다', () => {
        expect(selectTab({ tab: 'my', snap: 'half' }, 'my')).toEqual({
            tab: 'my',
            snap: 'collapsed',
        });
        expect(selectTab({ tab: 'my', snap: 'full' }, 'my')).toEqual({
            tab: 'my',
            snap: 'collapsed',
        });
        expect(selectTab({ tab: 'my', snap: 'collapsed' }, 'my')).toEqual({
            tab: 'my',
            snap: 'half',
        });
    });

    it('검색 탭은 시트가 없어 단계를 바꾸지 않는다', () => {
        expect(selectTab({ tab: 'search', snap: 'half' }, 'search')).toEqual({
            tab: 'search',
            snap: 'half',
        });
    });
});
