import { describe, expect, it } from 'vitest';

import { reportMarkerLabel } from './reportMarkers';
import type { RouteReport } from './routeApi';

const report: RouteReport = {
    id: 1,
    kind: 'construction',
    description: '  보도 공사 중  ',
    position: [126.97, 37.56],
};

describe('reportMarkerLabel', () => {
    it('유형과 설명을 함께 적는다', () => {
        expect(reportMarkerLabel(report)).toBe('제보 공사: 보도 공사 중');
    });

    it('설명이 없으면 유형만 적는다', () => {
        expect(reportMarkerLabel({ ...report, description: null })).toBe(
            '제보 공사',
        );
        expect(reportMarkerLabel({ ...report, description: '   ' })).toBe(
            '제보 공사',
        );
    });
});
