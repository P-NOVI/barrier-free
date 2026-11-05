import { describe, expect, it } from 'vitest';

import type { LngLat } from './kakaoMap';
import { categoryLabel, toPickedPlace } from './selection';

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

describe('categoryLabel', () => {
    it('마지막 단계를 쓴다', () => {
        expect(
            categoryLabel('부동산 > 주거시설 > 아파트', '청담더마크아파트'),
        ).toBe('아파트');
    });

    it('마지막 단계가 상호면 한 단계 위를 쓴다', () => {
        expect(
            categoryLabel(
                '음식점 > 카페 > 커피전문점 > 커피빈',
                '커피빈 부천역점',
            ),
        ).toBe('커피전문점');
    });

    it('한 단계뿐이면 이름과 상관없이 그대로 쓴다', () => {
        expect(categoryLabel('카페', '카페 봄')).toBe('카페');
    });

    it('분류가 비어 있으면 null', () => {
        expect(categoryLabel('', '서울역')).toBeNull();
    });
});
