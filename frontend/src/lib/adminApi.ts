// 관리자 제보 검토. 요청·응답 형식은 backend/app/routers/admin.py 와 같다.

import { type ApiOptions, apiUrl, requestJson } from './apiClient';
import { inOrder } from './historyApi';
import type { Report, ReportStatus } from './reportApi';

export type AdminReport = Report & {
    /** 관리자만 열 수 있는 사진 주소. apiUrl 로 풀어서 쓴다. */
    photo_url: string;
};

/** 상태별 제보. 오래된 것부터 온다. 관리자가 아니면 401·403 */
export async function fetchReports(
    status: ReportStatus,
    options?: ApiOptions,
): Promise<AdminReport[]> {
    const { reports } = await requestJson<{ reports: AdminReport[] }>(
        {
            path: '/api/admin/reports',
            query: { report_status: status },
            failureMessage: '제보를 불러오지 못했습니다.',
        },
        options,
    );
    return reports;
}

/** 승인한다. 이미 검토가 끝난 제보면 409 */
export function approveReport(
    id: number,
    options?: ApiOptions,
): Promise<AdminReport> {
    return inOrder(() =>
        requestJson<AdminReport>(
            {
                path: `/api/admin/reports/${id}/approve`,
                method: 'POST',
                failureMessage: '제보를 승인하지 못했습니다.',
            },
            options,
        ),
    );
}

/** 취소한다. 이미 검토가 끝난 제보면 409 */
export function cancelReport(
    id: number,
    options?: ApiOptions,
): Promise<AdminReport> {
    return inOrder(() =>
        requestJson<AdminReport>(
            {
                path: `/api/admin/reports/${id}/cancel`,
                method: 'POST',
                failureMessage: '제보를 취소하지 못했습니다.',
            },
            options,
        ),
    );
}

/** 승인한 제보를 해결됨으로 바꾼다. 승인한 제보가 아니면 409 */
export function resolveReport(
    id: number,
    options?: ApiOptions,
): Promise<AdminReport> {
    return inOrder(() =>
        requestJson<AdminReport>(
            {
                path: `/api/admin/reports/${id}/resolve`,
                method: 'POST',
                failureMessage: '제보를 해결됨으로 바꾸지 못했습니다.',
            },
            options,
        ),
    );
}

/** 만료된 제보는 취소만 할 수 있다. 서버도 승인을 막는다(report_expired). */
export function isReportExpired(
    report: Pick<AdminReport, 'expires_at'>,
    now: number,
): boolean {
    return new Date(report.expires_at).getTime() <= now;
}

/** <img> 에 넣는 사진 주소 */
export function reportPhotoUrl(report: AdminReport, baseUrl?: string): string {
    return apiUrl(report.photo_url, baseUrl);
}
