import { afterEach, describe, expect, it, vi } from 'vitest';

import {
    type AdminReport,
    approveReport,
    cancelReport,
    fetchReports,
    isReportExpired,
    reportPhotoUrl,
    resolveReport,
} from './adminApi';
import { ApiError } from './apiClient';

const OPTIONS = { baseUrl: 'http://api.test' };

afterEach(() => {
    vi.unstubAllGlobals();
});

describe('관리자 제보 API', () => {
    it('상태별 제보 목록을 쿠키와 함께 가져온다', async () => {
        const reports = [{ id: 1 }, { id: 2 }];
        const fetchMock = vi
            .fn()
            .mockImplementation(
                async () => new Response(JSON.stringify({ reports })),
            );
        vi.stubGlobal('fetch', fetchMock);

        await expect(fetchReports('pending', OPTIONS)).resolves.toEqual(
            reports,
        );
        await fetchReports('approved', OPTIONS);
        await fetchReports('resolved', OPTIONS);
        await fetchReports('rejected', OPTIONS);

        const urls = fetchMock.mock.calls.map(([url]) => String(url));
        expect(urls).toEqual([
            'http://api.test/api/admin/reports?report_status=pending',
            'http://api.test/api/admin/reports?report_status=approved',
            'http://api.test/api/admin/reports?report_status=resolved',
            'http://api.test/api/admin/reports?report_status=rejected',
        ]);
        expect(fetchMock.mock.calls[0][1].credentials).toBe('include');
    });

    it('관리자가 아니면 안내 문구와 이유를 오류로 던진다', async () => {
        const detail = {
            reason: 'admin_only',
            message: '관리자만 쓸 수 있습니다.',
        };
        vi.stubGlobal(
            'fetch',
            vi
                .fn()
                .mockResolvedValue(
                    new Response(JSON.stringify({ detail }), { status: 403 }),
                ),
        );

        await expect(fetchReports('pending', OPTIONS)).rejects.toEqual(
            new ApiError(detail.message, detail.reason),
        );
    });

    it('승인은 approve 로 POST 한다', async () => {
        const saved = { id: 7, status: 'approved' };
        const fetchMock = vi
            .fn()
            .mockResolvedValue(new Response(JSON.stringify(saved)));
        vi.stubGlobal('fetch', fetchMock);

        await expect(approveReport(7, OPTIONS)).resolves.toEqual(saved);

        const [url, init] = fetchMock.mock.calls[0];
        expect(String(url)).toBe('http://api.test/api/admin/reports/7/approve');
        expect(init.method).toBe('POST');
        expect(init.credentials).toBe('include');
    });

    it('취소는 cancel 로 POST 한다', async () => {
        const saved = { id: 7, status: 'rejected' };
        const fetchMock = vi
            .fn()
            .mockResolvedValue(new Response(JSON.stringify(saved)));
        vi.stubGlobal('fetch', fetchMock);

        await expect(cancelReport(7, OPTIONS)).resolves.toEqual(saved);

        const [url, init] = fetchMock.mock.calls[0];
        expect(String(url)).toBe('http://api.test/api/admin/reports/7/cancel');
        expect(init.method).toBe('POST');
    });

    it('해결됨 처리는 resolve 로 POST 한다', async () => {
        const saved = { id: 7, status: 'resolved' };
        const fetchMock = vi
            .fn()
            .mockResolvedValue(new Response(JSON.stringify(saved)));
        vi.stubGlobal('fetch', fetchMock);

        await expect(resolveReport(7, OPTIONS)).resolves.toEqual(saved);

        const [url, init] = fetchMock.mock.calls[0];
        expect(String(url)).toBe('http://api.test/api/admin/reports/7/resolve');
        expect(init.method).toBe('POST');
        expect(init.credentials).toBe('include');
    });

    it('승인한 제보가 아니면 안내 문구를 오류로 던진다', async () => {
        const detail = {
            reason: 'report_not_approved',
            message: '승인된 제보만 해결됨으로 바꿀 수 있습니다.',
        };
        vi.stubGlobal(
            'fetch',
            vi
                .fn()
                .mockResolvedValue(
                    new Response(JSON.stringify({ detail }), { status: 409 }),
                ),
        );

        await expect(resolveReport(7, OPTIONS)).rejects.toEqual(
            new ApiError(detail.message, detail.reason),
        );
    });

    it('이미 검토한 제보를 다시 검토하면 안내 문구를 오류로 던진다', async () => {
        const detail = {
            reason: 'report_not_pending',
            message: '이미 검토가 끝난 제보입니다.',
        };
        vi.stubGlobal(
            'fetch',
            vi
                .fn()
                .mockResolvedValue(
                    new Response(JSON.stringify({ detail }), { status: 409 }),
                ),
        );

        await expect(approveReport(7, OPTIONS)).rejects.toEqual(
            new ApiError(detail.message, detail.reason),
        );
    });

    it('만료 시각이 지났거나 같으면 만료로 본다', () => {
        const now = Date.parse('2026-11-06T00:00:00Z');

        expect(
            isReportExpired({ expires_at: '2026-11-05T23:59:59Z' }, now),
        ).toBe(true);
        expect(
            isReportExpired({ expires_at: '2026-11-06T00:00:00Z' }, now),
        ).toBe(true);
        expect(
            isReportExpired({ expires_at: '2026-11-06T00:00:01Z' }, now),
        ).toBe(false);
    });

    it('사진 주소는 API 주소 기준으로 만든다', () => {
        const report = { photo_url: '/api/admin/reports/3/photo' };

        expect(reportPhotoUrl(report as AdminReport, 'http://api.test')).toBe(
            'http://api.test/api/admin/reports/3/photo',
        );
    });
});
