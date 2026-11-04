import { describe, expect, it } from 'vitest';

import {
    clampDrag,
    selectTab,
    SNAP_THRESHOLD_PX,
    snapAfterDrag,
    TAP_SLOP_PX,
} from './sheet';

describe('clampDrag', () => {
    it('펼친 시트는 아래로만 끌린다', () => {
        expect(clampDrag('half', -30, 300)).toBe(0);
        expect(clampDrag('half', 120, 300)).toBe(120);
        expect(clampDrag('half', 500, 300)).toBe(300);
    });

    it('접은 시트는 위로만 끌린다', () => {
        expect(clampDrag('collapsed', 30, 300)).toBe(0);
        expect(clampDrag('collapsed', -120, 300)).toBe(-120);
        expect(clampDrag('collapsed', -500, 300)).toBe(-300);
    });
});

describe('snapAfterDrag', () => {
    it('조금만 움직이면 누른 것으로 보고 단계를 바꾼다', () => {
        expect(snapAfterDrag('half', TAP_SLOP_PX - 1)).toBe('collapsed');
        expect(snapAfterDrag('collapsed', 0)).toBe('half');
    });

    it('기준보다 많이 끌면 다음 단계로 간다', () => {
        expect(snapAfterDrag('half', SNAP_THRESHOLD_PX + 1)).toBe('collapsed');
        expect(snapAfterDrag('collapsed', -SNAP_THRESHOLD_PX - 1)).toBe('half');
    });

    it('덜 끌면 원래 단계로 돌아간다', () => {
        expect(snapAfterDrag('half', SNAP_THRESHOLD_PX - 1)).toBe('half');
        expect(snapAfterDrag('collapsed', -SNAP_THRESHOLD_PX + 1)).toBe(
            'collapsed',
        );
    });
});

describe('selectTab', () => {
    it('다른 탭을 누르면 절반으로 연다', () => {
        expect(selectTab({ tab: 'route', snap: 'collapsed' }, 'my')).toEqual({
            tab: 'my',
            snap: 'half',
        });
    });

    it('열린 탭을 다시 누르면 접거나 편다', () => {
        expect(selectTab({ tab: 'my', snap: 'half' }, 'my')).toEqual({
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
