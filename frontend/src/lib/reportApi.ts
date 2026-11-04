// 길 위 문제 제보. 요청·응답 형식은 backend/app/routers/reports.py 와 같다.

import { type ApiOptions, requestJson } from './apiClient';
import type { LngLat } from './kakaoMap';

// backend/app/services/report_service.py 의 REPORT_KINDS 와 같다.
export const REPORT_KINDS = [
    { id: 'curb', label: '턱' },
    { id: 'construction', label: '공사' },
    { id: 'obstacle', label: '장애물' },
    { id: 'damage', label: '파손' },
] as const;

export type ReportKind = (typeof REPORT_KINDS)[number]['id'];

/** 공사 제보에서만 통행 불가를 고를 수 있다. */
export const BLOCKABLE_KIND: ReportKind = 'construction';

// backend/app/config.py 의 report_photo_max_bytes 와 같다.
export const PHOTO_MAX_BYTES = 5 * 1024 * 1024;

export type ReportRequest = {
    kind: ReportKind;
    /** 지나갈 수 없는 공사인지. 공사가 아니면 false */
    blocked: boolean;
    position: LngLat;
    photo: File;
};

export type Report = {
    id: number;
    kind: ReportKind;
    blocked: boolean;
    status: 'pending' | 'approved' | 'rejected';
    lon: number;
    lat: number;
    created_at: string;
    expires_at: string;
};

export function toReportForm({
    kind,
    blocked,
    position,
    photo,
}: ReportRequest): FormData {
    const form = new FormData();
    form.set('kind', kind);
    form.set('blocked', String(kind === BLOCKABLE_KIND && blocked));
    form.set('lon', String(position[0]));
    form.set('lat', String(position[1]));
    form.set('photo', photo);
    return form;
}

/** 제보는 관리자가 승인하기 전까지 대기 상태로 저장된다. */
export function submitReport(
    request: ReportRequest,
    options?: ApiOptions,
): Promise<Report> {
    return requestJson<Report>(
        {
            path: '/api/reports',
            body: toReportForm(request),
            failureMessage: '제보를 보내지 못했습니다.',
        },
        options,
    );
}
