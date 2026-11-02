import { describe, expect, it } from 'vitest';

import type { LngLat } from './kakaoMap';
import { NO_ENDPOINTS, selectEndpoint } from './selection';

const A: LngLat = [126.97, 37.55];
const B: LngLat = [126.98, 37.56];
const C: LngLat = [126.99, 37.57];

describe('selectEndpoint', () => {
    it('처음 누른 곳은 출발지', () => {
        expect(selectEndpoint(NO_ENDPOINTS, A)).toEqual({
            start: A,
            goal: null,
        });
    });

    it('두 번째 누른 곳은 도착지', () => {
        expect(selectEndpoint({ start: A, goal: null }, B)).toEqual({
            start: A,
            goal: B,
        });
    });

    it('둘 다 고른 뒤 누르면 새 출발지로 다시 시작', () => {
        expect(selectEndpoint({ start: A, goal: B }, C)).toEqual({
            start: C,
            goal: null,
        });
    });
});
