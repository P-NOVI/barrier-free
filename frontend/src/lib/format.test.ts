import { describe, expect, it } from 'vitest';

import { formatDistance, formatGrade } from './format';

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

describe('formatGrade', () => {
    it('비율을 백분율 소수 첫째 자리로', () => {
        expect(formatGrade(0.0491)).toBe('4.9%');
        expect(formatGrade(0)).toBe('0.0%');
    });
});
