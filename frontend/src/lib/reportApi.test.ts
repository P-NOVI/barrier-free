import { afterEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from './apiClient';
import { type ReportRequest, submitReport, toReportForm } from './reportApi';

const OPTIONS = { baseUrl: 'http://api.test' };
const CITY_HALL: [number, number] = [126.9779, 37.5663];

function request(overrides: Partial<ReportRequest> = {}): ReportRequest {
    return {
        kind: 'curb',
        blocked: false,
        position: CITY_HALL,
        photo: new File(['x'], 'a.jpg', { type: 'image/jpeg' }),
        ...overrides,
    };
}

afterEach(() => {
    vi.unstubAllGlobals();
});

describe('제보 폼 데이터', () => {
    it('유형·좌표·사진을 담는다', () => {
        const form = toReportForm(request({ kind: 'obstacle' }));

        expect(form.get('kind')).toBe('obstacle');
        expect(form.get('lon')).toBe('126.9779');
        expect(form.get('lat')).toBe('37.5663');
        expect(form.get('blocked')).toBe('false');
        expect((form.get('photo') as File).name).toBe('a.jpg');
    });

    it('사진 설명은 앞뒤 공백을 자르고, 없으면 빈 값을 보낸다', () => {
        expect(
            toReportForm(request({ description: '  턱이 높아요 ' })).get(
                'description',
            ),
        ).toBe('턱이 높아요');
        expect(toReportForm(request()).get('description')).toBe('');
    });

    it('공사만 통행 불가를 보낸다', () => {
        expect(
            toReportForm(request({ kind: 'construction', blocked: true })).get(
                'blocked',
            ),
        ).toBe('true');
        // 공사가 아닌 유형으로 바꿨는데 이전 선택이 남아 있어도 보내지 않는다.
        expect(
            toReportForm(request({ kind: 'curb', blocked: true })).get(
                'blocked',
            ),
        ).toBe('false');
    });
});

describe('제보 API', () => {
    it('쿠키와 함께 폼 데이터를 보낸다', async () => {
        const saved = { id: 1, status: 'pending' };
        const fetchMock = vi
            .fn()
            .mockResolvedValue(new Response(JSON.stringify(saved)));
        vi.stubGlobal('fetch', fetchMock);

        await expect(submitReport(request(), OPTIONS)).resolves.toEqual(saved);

        const [url, init] = fetchMock.mock.calls[0];
        expect(String(url)).toBe('http://api.test/api/reports');
        expect(init.method).toBe('POST');
        expect(init.credentials).toBe('include');
        expect(init.body).toBeInstanceOf(FormData);
        // JSON 헤더를 붙이면 브라우저가 multipart 경계를 정하지 못한다.
        expect(init.headers).toBeUndefined();
    });

    it('서버가 거절하면 안내 문구를 오류로 던진다', async () => {
        const detail = {
            reason: 'bad_photo',
            message: '사진만 올릴 수 있습니다.',
        };
        vi.stubGlobal(
            'fetch',
            vi
                .fn()
                .mockResolvedValue(
                    new Response(JSON.stringify({ detail }), { status: 422 }),
                ),
        );

        await expect(submitReport(request(), OPTIONS)).rejects.toEqual(
            new ApiError(detail.message, detail.reason),
        );
    });
});
