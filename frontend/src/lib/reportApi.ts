// 길 위 문제 제보. 요청·응답 형식은 backend/app/routers/reports.py 와 같다.

import { type ApiOptions, requestJson } from './apiClient';
import { inOrder } from './historyApi';
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

// backend/app/models.py 의 REPORT_DESCRIPTION_MAX_LENGTH 와 같다.
export const DESCRIPTION_MAX_LENGTH = 200;

export type ReportRequest = {
    kind: ReportKind;
    /** 지나갈 수 없는 공사인지. 공사가 아니면 false */
    blocked: boolean;
    position: LngLat;
    photo: File;
    /** 사진 설명. 비워도 된다. */
    description?: string;
};

export type ReportStatus = 'pending' | 'approved' | 'rejected';

export const REPORT_STATUS_LABELS: Record<ReportStatus, string> = {
    pending: '검토 중',
    approved: '승인됨',
    rejected: '반려됨',
};

/** 위치와 사진은 고칠 수 없다. 보낸 항목만 바뀐다. */
export type ReportUpdate = {
    kind?: ReportKind;
    blocked?: boolean;
    /** 빈 문자열이면 설명을 지운다. */
    description?: string;
};

export type Report = {
    id: number;
    kind: ReportKind;
    blocked: boolean;
    status: ReportStatus;
    description: string | null;
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
    description,
}: ReportRequest): FormData {
    const form = new FormData();
    form.set('kind', kind);
    form.set('blocked', String(kind === BLOCKABLE_KIND && blocked));
    form.set('lon', String(position[0]));
    form.set('lat', String(position[1]));
    form.set('photo', photo);
    form.set('description', description?.trim() ?? '');
    return form;
}

export function reportKindLabel(kind: ReportKind): string {
    return REPORT_KINDS.find((option) => option.id === kind)?.label ?? kind;
}

/** 내가 올린 제보. 쿠키의 사용자(게스트·회원) 것만 온다. */
export async function fetchMyReports(options?: ApiOptions): Promise<Report[]> {
    const { reports } = await requestJson<{ reports: Report[] }>(
        {
            path: '/api/me/reports',
            failureMessage: '내 제보를 불러오지 못했습니다.',
        },
        options,
    );
    return reports;
}

/** 검토 중(pending)인 제보만 고칠 수 있다. */
export function updateReport(
    id: number,
    update: ReportUpdate,
    options?: ApiOptions,
): Promise<Report> {
    return inOrder(() =>
        requestJson<Report>(
            {
                path: `/api/me/reports/${id}`,
                method: 'PATCH',
                body: update,
                failureMessage: '제보를 고치지 못했습니다.',
            },
            options,
        ),
    );
}

export function deleteReport(id: number, options?: ApiOptions): Promise<void> {
    return inOrder(() =>
        requestJson<void>(
            {
                path: `/api/me/reports/${id}`,
                method: 'DELETE',
                failureMessage: '제보를 지우지 못했습니다.',
            },
            options,
        ),
    );
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
