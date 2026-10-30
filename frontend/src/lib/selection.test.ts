import { describe, expect, it } from 'vitest';

import type { LngLat } from './kakaoMap';
import {
    type Endpoint,
    MAP_CLICK_LABEL,
    NO_ENDPOINTS,
    renameEndpoint,
    selectEndpoint,
} from './selection';

const A: LngLat = [126.97, 37.55];
const B: LngLat = [126.98, 37.56];
const C: LngLat = [126.99, 37.57];

function clicked(position: LngLat): Endpoint {
    return { position, label: MAP_CLICK_LABEL };
}

describe('selectEndpoint', () => {
    it('처음 누른 곳은 출발지', () => {
        expect(selectEndpoint(NO_ENDPOINTS, A)).toEqual({
            start: clicked(A),
            goal: null,
        });
    });

    it('두 번째 누른 곳은 도착지', () => {
        expect(selectEndpoint({ start: clicked(A), goal: null }, B)).toEqual({
            start: clicked(A),
            goal: clicked(B),
        });
    });

    it('검색으로 고른 출발지는 그대로 두고 도착지만 정한다', () => {
        const searched = { position: A, label: '서울역' };
        expect(selectEndpoint({ start: searched, goal: null }, B)).toEqual({
            start: searched,
            goal: clicked(B),
        });
    });

    it('둘 다 고른 뒤 누르면 새 출발지로 다시 시작', () => {
        expect(
            selectEndpoint({ start: clicked(A), goal: clicked(B) }, C),
        ).toEqual({
            start: clicked(C),
            goal: null,
        });
    });
});

describe('renameEndpoint', () => {
    it('같은 클릭으로 고른 출발·도착만 이름을 바꾼다', () => {
        const current = { start: clicked(A), goal: clicked(B) };

        expect(
            renameEndpoint(current, current.goal.position, '덕수궁'),
        ).toEqual({
            start: clicked(A),
            goal: { position: B, label: '덕수궁' },
        });
    });

    it('값이 같아도 다른 클릭이면 바꾸지 않는다', () => {
        const current = { start: clicked(A), goal: null };

        expect(renameEndpoint(current, [...A] as LngLat, '서울역')).toBe(
            current,
        );
    });
});
