import { afterEach, describe, expect, it, vi } from 'vitest';

import { fetchCongestion, type SensorCongestion } from './congestionApi';

const BASE_URL = 'http://api.test';
const SENSOR: SensorCongestion = {
    code: 3032,
    position: [126.84, 37.54],
    address: '서울특별시 강서구 화곡동 668-10',
    visitor_count: 208,
    measured_at: '2026-11-02T11:18:00+09:00',
};

afterEach(() => {
    vi.unstubAllGlobals();
});

describe('fetchCongestion', () => {
    it('GET 하고 센서 목록을 돌려준다', async () => {
        const fetchMock = vi.fn().mockResolvedValue(
            new Response(JSON.stringify({ sensors: [SENSOR] }), {
                status: 200,
            }),
        );
        vi.stubGlobal('fetch', fetchMock);

        await expect(fetchCongestion({ baseUrl: BASE_URL })).resolves.toEqual([
            SENSOR,
        ]);

        const [url, init] = fetchMock.mock.calls[0];
        expect(String(url)).toBe('http://api.test/api/congestion');
        expect(init.method).toBeUndefined();
    });

    it('혼잡도 키가 없다는 백엔드 안내를 그대로 쓴다', async () => {
        vi.stubGlobal(
            'fetch',
            vi.fn().mockResolvedValue(
                new Response(
                    JSON.stringify({
                        detail: {
                            reason: 'congestion_unavailable',
                            message: '혼잡도 키가 없습니다.',
                        },
                    }),
                    { status: 503 },
                ),
            ),
        );

        await expect(
            fetchCongestion({ baseUrl: BASE_URL }),
        ).rejects.toMatchObject({
            reason: 'congestion_unavailable',
            message: '혼잡도 키가 없습니다.',
        });
    });
});
