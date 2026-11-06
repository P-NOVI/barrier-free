import { describe, expect, it } from 'vitest';

import {
    DEPART_NOW,
    departHours,
    isDepartTimeValid,
    kstHour,
    toDepartAt,
} from './departTime';

// 2026-11-06 14:25 KST
const NOW = new Date('2026-11-06T05:25:00Z');
// 2026-11-06 23:40 KST (UTC 로는 아직 14시)
const LATE = new Date('2026-11-06T14:40:00Z');

describe('departHours', () => {
    it('오늘은 지금 시부터, 내일·모레는 0시부터 고를 수 있다', () => {
        expect(kstHour(NOW)).toBe(14);
        expect(departHours(0, NOW)).toEqual([
            14, 15, 16, 17, 18, 19, 20, 21, 22, 23,
        ]);
        expect(departHours(1, NOW)).toHaveLength(24);
        expect(departHours(2, NOW)[0]).toBe(0);
    });

    it('한국 시각 기준이라 밤 11시에는 오늘 23시만 남는다', () => {
        expect(departHours(0, LATE)).toEqual([23]);
    });
});

describe('isDepartTimeValid', () => {
    it('지난 시각과 모레 뒤는 고를 수 없다', () => {
        expect(isDepartTimeValid(DEPART_NOW, NOW)).toBe(true);
        expect(isDepartTimeValid({ kind: 'at', day: 0, hour: 14 }, NOW)).toBe(
            true,
        );
        expect(isDepartTimeValid({ kind: 'at', day: 0, hour: 13 }, NOW)).toBe(
            false,
        );
        expect(isDepartTimeValid({ kind: 'at', day: 2, hour: 23 }, NOW)).toBe(
            true,
        );
        expect(isDepartTimeValid({ kind: 'at', day: 3, hour: 0 }, NOW)).toBe(
            false,
        );
    });
});

describe('toDepartAt', () => {
    it('지금이면 null, 아니면 한국 시각 정시', () => {
        expect(toDepartAt(DEPART_NOW, NOW)).toBeNull();
        expect(toDepartAt({ kind: 'at', day: 1, hour: 9 }, NOW)).toBe(
            '2026-11-07T09:00:00+09:00',
        );
    });

    it('달이 바뀌는 날도 날짜를 넘긴다', () => {
        // 2026-11-30 10:00 KST
        const endOfMonth = new Date('2026-11-30T01:00:00Z');
        expect(toDepartAt({ kind: 'at', day: 2, hour: 0 }, endOfMonth)).toBe(
            '2026-12-02T00:00:00+09:00',
        );
    });

    it('UTC 로는 전날이어도 한국 날짜로 계산한다', () => {
        // 2026-11-07 08:00 KST = 2026-11-06 23:00 UTC
        const morning = new Date('2026-11-06T23:00:00Z');
        expect(toDepartAt({ kind: 'at', day: 0, hour: 9 }, morning)).toBe(
            '2026-11-07T09:00:00+09:00',
        );
    });
});
