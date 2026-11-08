// 길찾기 경로 위 제보 마커에 쓰는 문구. 지도 그리기와 분리해 테스트한다.

import type { RouteReport } from './routeApi';
import { reportKindLabel } from './reportApi';

/** 마커 접근성 이름. 스크린 리더가 유형과 설명을 함께 읽는다. */
export function reportMarkerLabel(report: RouteReport): string {
    const kind = reportKindLabel(report.kind);
    const description = report.description?.trim();
    return description ? `제보 ${kind}: ${description}` : `제보 ${kind}`;
}
