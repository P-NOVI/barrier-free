import { describe, expect, it } from 'vitest';

import { add } from './add';

describe('add', () => {
    it('두 수를 더한다', () => {
        expect(add(1, 2)).toBe(3);
    });
});
