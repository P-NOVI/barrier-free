import { describe, expect, it } from 'vitest';

import type { LngLat } from './kakaoMap';
import {
    categoryLabel,
    isEndpointRole,
    NO_ENDPOINTS,
    shortcutRole,
    toPickedPlace,
} from './selection';

const A: LngLat = [126.97, 37.55];

describe('shortcutRole', () => {
    const filled = { position: A, label: '집' };

    it('누르고 있던 칸이 있으면 그 칸에 넣는다', () => {
        expect(shortcutRole('goal', NO_ENDPOINTS)).toBe('goal');
        expect(shortcutRole('start', { start: filled, goal: filled })).toBe(
            'start',
        );
    });

    it('누른 칸이 없으면 빈 칸에 넣는다(출발지 먼저)', () => {
        expect(shortcutRole(null, NO_ENDPOINTS)).toBe('start');
        expect(shortcutRole(null, { start: filled, goal: null })).toBe('goal');
        expect(shortcutRole(null, { start: null, goal: filled })).toBe('start');
    });

    it('둘 다 차 있으면 도착지를 바꾼다', () => {
        expect(shortcutRole(null, { start: filled, goal: filled })).toBe(
            'goal',
        );
    });
});

describe('isEndpointRole', () => {
    it('출발지·도착지만 맞다', () => {
        expect(isEndpointRole('start')).toBe(true);
        expect(isEndpointRole('goal')).toBe(true);
        expect(isEndpointRole(undefined)).toBe(false);
        expect(isEndpointRole('home')).toBe(false);
    });
});

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
