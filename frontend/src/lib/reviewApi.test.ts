import { afterEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from './apiClient';
import { submitReview } from './reviewApi';

const OPTIONS = { baseUrl: 'http://api.test' };

afterEach(() => {
    vi.unstubAllGlobals();
});

describe('제보 리뷰 API', () => {
    it('쿠키와 함께 상태와 한마디를 JSON 으로 보낸다', async () => {
        const saved = { id: 1, report_id: 7, outcome: 'improved', comment: '' };
        const fetchMock = vi
            .fn()
            .mockResolvedValue(new Response(JSON.stringify(saved)));
        vi.stubGlobal('fetch', fetchMock);

        await expect(
            submitReview(
                7,
                { outcome: 'improved', comment: '  좋아졌어요 ' },
                OPTIONS,
            ),
        ).resolves.toEqual(saved);

        const [url, init] = fetchMock.mock.calls[0];
        expect(String(url)).toBe('http://api.test/api/reports/7/review');
        expect(init.method).toBe('POST');
        expect(init.credentials).toBe('include');
        expect(JSON.parse(init.body)).toEqual({
            outcome: 'improved',
            comment: '좋아졌어요',
        });
    });

    it('한마디를 안 쓰면 빈 문자열을 보낸다', async () => {
        const fetchMock = vi.fn().mockResolvedValue(new Response('{}'));
        vi.stubGlobal('fetch', fetchMock);

        await submitReview(7, { outcome: 'same' }, OPTIONS);

        expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
            outcome: 'same',
            comment: '',
        });
    });

    it('서버가 거절하면 안내 문구를 오류로 던진다', async () => {
        const detail = {
            reason: 'report_not_reviewable',
            message: '리뷰를 받지 않는 제보입니다.',
        };
        vi.stubGlobal(
            'fetch',
            vi
                .fn()
                .mockResolvedValue(
                    new Response(JSON.stringify({ detail }), { status: 409 }),
                ),
        );

        await expect(
            submitReview(7, { outcome: 'gone' }, OPTIONS),
        ).rejects.toEqual(new ApiError(detail.message, detail.reason));
    });
});
