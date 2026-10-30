import { describe, expect, it } from 'vitest';

import type { LngLat } from './kakaoMap';
import { toPickedPlace } from './selection';

const A: LngLat = [126.97, 37.55];

describe('toPickedPlace', () => {
    it('찾은 이름과 주소를 담는다', () => {
        expect(
            toPickedPlace(A, { name: '서울역', address: '봉래동2가' }),
        ).toEqual({ position: A, name: '서울역', address: '봉래동2가' });
    });

    it('주소가 빈 문자열이면 null 로 둔다', () => {
        expect(toPickedPlace(A, { name: '시청앞', address: '' })).toEqual({
            position: A,
            name: '시청앞',
            address: null,
        });
    });

    it('찾지 못하면 이름·주소가 null', () => {
        expect(toPickedPlace(A, null)).toEqual({
            position: A,
            name: null,
            address: null,
        });
    });
});
