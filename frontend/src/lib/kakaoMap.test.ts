import { afterEach, describe, expect, it, vi } from 'vitest';

import { loadKakaoMaps, sdkUrl, toLatLng, toLngLat } from './kakaoMap';

class FakeLatLng {
    private readonly lat: number;
    private readonly lng: number;

    constructor(lat: number, lng: number) {
        this.lat = lat;
        this.lng = lng;
    }

    getLat(): number {
        return this.lat;
    }

    getLng(): number {
        return this.lng;
    }
}

afterEach(() => {
    vi.unstubAllGlobals();
});

describe('sdkUrl', () => {
    it('앱 키와 autoload=false 를 붙인다', () => {
        const url = new URL(sdkUrl('test-key'));
        expect(url.origin + url.pathname).toBe(
            'https://dapi.kakao.com/v2/maps/sdk.js',
        );
        expect(url.searchParams.get('appkey')).toBe('test-key');
        expect(url.searchParams.get('autoload')).toBe('false');
    });
});

describe('좌표 변환', () => {
    it('[lng, lat] 를 LatLng(lat, lng) 로 바꾼다', () => {
        vi.stubGlobal('kakao', { maps: { LatLng: FakeLatLng } });
        const latLng = toLatLng([126.9779, 37.5663]);
        expect(latLng.getLat()).toBe(37.5663);
        expect(latLng.getLng()).toBe(126.9779);
    });

    it('LatLng 를 [lng, lat] 로 되돌린다', () => {
        const latLng = new FakeLatLng(37.5663, 126.9779);
        expect(toLngLat(latLng as unknown as kakao.maps.LatLng)).toEqual([
            126.9779, 37.5663,
        ]);
    });
});

describe('loadKakaoMaps', () => {
    it('앱 키가 없으면 스크립트를 넣지 않고 실패한다', async () => {
        await expect(loadKakaoMaps('')).rejects.toThrow(
            'VITE_KAKAO_MAP_APP_KEY',
        );
    });
});
