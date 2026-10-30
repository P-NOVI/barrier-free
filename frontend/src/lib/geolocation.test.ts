import { describe, expect, it, vi } from 'vitest';

import { getCurrentPosition } from './geolocation';

type Outcome =
    { lng: number; lat: number; accuracy: number } | { code: number };

const DENIED = { code: 1 };
const TIMEOUT = { code: 3 };

/** getCurrentPosition 을 부를 때마다 outcomes 를 차례로 돌려주는 가짜 Geolocation */
function fakeGeolocation(...outcomes: Outcome[]) {
    const getCurrentPosition = vi.fn<Geolocation['getCurrentPosition']>(
        (success: PositionCallback, failure?: PositionErrorCallback | null) => {
            const outcome = outcomes.shift();
            if (outcome && 'lng' in outcome) {
                success({
                    coords: {
                        longitude: outcome.lng,
                        latitude: outcome.lat,
                        accuracy: outcome.accuracy,
                    },
                } as GeolocationPosition);
            } else {
                failure?.(outcome as GeolocationPositionError);
            }
        },
    );
    return {
        geolocation: { getCurrentPosition } as unknown as Geolocation,
        getCurrentPosition,
    };
}

describe('getCurrentPosition', () => {
    it('정확한 위치를 [경도, 위도] 와 오차 반경으로 돌려준다', async () => {
        const { geolocation, getCurrentPosition: call } = fakeGeolocation({
            lng: 126.97,
            lat: 37.56,
            accuracy: 15,
        });

        await expect(getCurrentPosition(geolocation)).resolves.toEqual({
            position: [126.97, 37.56],
            accuracy: 15,
        });
        expect(call.mock.calls[0][2]).toMatchObject({
            enableHighAccuracy: true,
        });
    });

    it('정확한 위치가 실패하면 대략적인 위치로 다시 묻는다', async () => {
        const { geolocation, getCurrentPosition: call } = fakeGeolocation(
            TIMEOUT,
            { lng: 126.98, lat: 37.57, accuracy: 1200 },
        );

        await expect(getCurrentPosition(geolocation)).resolves.toEqual({
            position: [126.98, 37.57],
            accuracy: 1200,
        });
        expect(call.mock.calls[1][2]).toMatchObject({
            enableHighAccuracy: false,
        });
    });

    it('권한이 없으면 다시 묻지 않고 권한 안내를 한다', async () => {
        const { geolocation, getCurrentPosition: call } =
            fakeGeolocation(DENIED);

        await expect(getCurrentPosition(geolocation)).rejects.toThrow(
            '위치 권한',
        );
        expect(call).toHaveBeenCalledTimes(1);
    });

    it('두 번 다 실패하면 검색을 안내한다', async () => {
        const { geolocation } = fakeGeolocation(TIMEOUT, TIMEOUT);

        await expect(getCurrentPosition(geolocation)).rejects.toThrow(
            '장소를 검색',
        );
    });

    it('위치 기능이 없는 브라우저를 알린다', async () => {
        await expect(getCurrentPosition(undefined)).rejects.toThrow('지원');
    });
});
