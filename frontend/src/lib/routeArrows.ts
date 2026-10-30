// 경로 선 안에 놓을 진행 방향 화살표 자리. 화면 좌표(px)로 계산한다.

export type ScreenPoint = { x: number; y: number };

export type RouteArrow = ScreenPoint & {
    /** 진행 방향(도). 오른쪽이 0, 화면 기준 시계 방향 */
    angle: number;
};

/** 꺾은선을 따라 spacing(px) 간격으로 화살표 자리를 고른다. 양 끝 반 간격 안에는 두지 않는다. */
export function arrowsAlong(
    points: ScreenPoint[],
    spacing: number,
): RouteArrow[] {
    if (spacing <= 0) {
        return [];
    }
    const segments = points.slice(1).map((to, i) => {
        const from = points[i];
        const dx = to.x - from.x;
        const dy = to.y - from.y;
        return { from, dx, dy, length: Math.hypot(dx, dy) };
    });
    const last =
        segments.reduce((sum, { length }) => sum + length, 0) - spacing / 2;
    const arrows: RouteArrow[] = [];
    let next = spacing / 2;
    let walked = 0;
    for (const { from, dx, dy, length } of segments) {
        if (length === 0) {
            continue;
        }
        const angle = (Math.atan2(dy, dx) * 180) / Math.PI;
        for (; next <= Math.min(walked + length, last); next += spacing) {
            const ratio = (next - walked) / length;
            arrows.push({
                x: from.x + dx * ratio,
                y: from.y + dy * ratio,
                angle,
            });
        }
        walked += length;
    }
    return arrows;
}
