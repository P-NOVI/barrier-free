import { describe, expect, it } from 'vitest';

import {
    formatClock,
    formatDistance,
    formatDuration,
    formatGrade,
} from './format';

describe('formatDistance', () => {
    it('1km 미만은 m 정수로', () => {
        expect(formatDistance(108.52)).toBe('109m');
        expect(formatDistance(999.4)).toBe('999m');
    });

    it('1km 이상은 km 소수 둘째 자리로', () => {
        expect(formatDistance(1000)).toBe('1.00km');
        expect(formatDistance(1616.6)).toBe('1.62km');
    });
});

describe('formatDuration', () => {
    it('분 단위로 반올림한다', () => {
        expect(formatDuration(338)).toBe('6분');
        expect(formatDuration(3569)).toBe('59분');
    });

    it('1분 미만은 1분으로', () => {
        expect(formatDuration(0)).toBe('1분');
        expect(formatDuration(20)).toBe('1분');
    });

    it('60분 이상은 시간과 분으로', () => {
        expect(formatDuration(3600)).toBe('1시간');
        expect(formatDuration(5100)).toBe('1시간 25분');
    });
});

describe('formatGrade', () => {
    it('비율을 백분율 소수 첫째 자리로', () => {
        expect(formatGrade(0.0491)).toBe('4.9%');
        expect(formatGrade(0)).toBe('0.0%');
    });
});

describe('formatClock', () => {
    it('ISO 시각에서 시:분만 꺼낸다', () => {
        expect(formatClock('2026-11-02T11:18:00+09:00')).toBe('11:18');
    });

    it('시각 형식이 아니면 그대로 돌려준다', () => {
        expect(formatClock('어제')).toBe('어제');
    });
});
