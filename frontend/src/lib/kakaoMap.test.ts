import { afterEach, describe, expect, it, vi } from 'vitest';

import {
    loadKakaoMaps,
    panToFit,
    sdkUrl,
    toLatLng,
    toLngLat,
} from './kakaoMap';

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

describe('panToFit', () => {
    const view = { width: 1000, height: 800 };
    const inset = { top: 48, right: 48, bottom: 48, left: 440 };

    it('이미 들어와 있으면 옮기지 않는다', () => {
        const box = { left: 500, top: 200, right: 760, bottom: 400 };
        expect(panToFit(box, view, inset)).toEqual([0, 0]);
    });

    it('위로 잘리면 그만큼 지도를 위로 옮긴다 (panBy 는 음수)', () => {
        const box = { left: 500, top: 10, right: 760, bottom: 200 };
        expect(panToFit(box, view, inset)).toEqual([0, -38]);
    });

    it('왼쪽 패널에 가리면 지도를 왼쪽으로 옮긴다', () => {
        const box = { left: 300, top: 200, right: 560, bottom: 400 };
        expect(panToFit(box, view, inset)).toEqual([-140, 0]);
    });

    it('오른쪽으로 잘리면 지도를 오른쪽으로 옮긴다', () => {
        const box = { left: 800, top: 200, right: 1060, bottom: 400 };
        expect(panToFit(box, view, inset)).toEqual([108, 0]);
    });
});
