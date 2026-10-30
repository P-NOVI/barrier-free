import { describe, expect, it } from 'vitest';

import { arrowsAlong } from './routeArrows';

describe('arrowsAlong', () => {
    it('양 끝 반 간격을 비우고 같은 간격으로 놓는다', () => {
        const arrows = arrowsAlong(
            [
                { x: 0, y: 0 },
                { x: 100, y: 0 },
            ],
            40,
        );

        expect(arrows).toEqual([
            { x: 20, y: 0, angle: 0 },
            { x: 60, y: 0, angle: 0 },
        ]);
    });

    it('꺾인 곳을 지나면 다음 선분 방향을 따른다', () => {
        const arrows = arrowsAlong(
            [
                { x: 0, y: 0 },
                { x: 30, y: 0 },
                { x: 30, y: 50 },
            ],
            40,
        );

        // 화면 아래쪽(y 증가)은 시계 방향 90도
        expect(arrows).toEqual([
            { x: 20, y: 0, angle: 0 },
            { x: 30, y: 30, angle: 90 },
        ]);
    });

    it('왼쪽으로 가면 180도', () => {
        const [arrow] = arrowsAlong(
            [
                { x: 50, y: 0 },
                { x: 0, y: 0 },
            ],
            40,
        );

        expect(arrow.angle).toBe(180);
    });

    it('겹친 점은 건너뛰고, 점이 하나면 놓지 않는다', () => {
        expect(
            arrowsAlong(
                [
                    { x: 0, y: 0 },
                    { x: 0, y: 0 },
                    { x: 0, y: 60 },
                ],
                40,
            ),
        ).toEqual([{ x: 0, y: 20, angle: 90 }]);
        expect(arrowsAlong([{ x: 0, y: 0 }], 40)).toEqual([]);
    });

    it('반 간격 두 개보다 짧으면 놓지 않는다', () => {
        expect(
            arrowsAlong(
                [
                    { x: 0, y: 0 },
                    { x: 30, y: 0 },
                ],
                40,
            ),
        ).toEqual([]);
    });
});
