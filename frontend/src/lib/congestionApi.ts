// GET /api/congestion 호출. 응답 형식은 backend/app/schemas.py 의 CongestionResponse 와 같다.

import { type ApiOptions, requestJson } from './apiClient';
import type { LngLat } from './kakaoMap';

/** S-DoT 센서 하나의 가장 최근 유동인구 */
export type SensorCongestion = {
    /** 센서 코드 */
    code: number;
    position: LngLat;
    /** 센서 설치 주소 */
    address: string;
    /** 유동인구 원시값(10분 단위 측정) */
    visitor_count: number;
    /** 측정 시각 (ISO 8601, 한국 시간) */
    measured_at: string;
};

export async function fetchCongestion(
    options?: ApiOptions,
): Promise<SensorCongestion[]> {
    const { sensors } = await requestJson<{ sensors: SensorCongestion[] }>(
        {
            path: '/api/congestion',
            failureMessage: '혼잡도를 가져오지 못했습니다.',
        },
        options,
    );
    return sensors;
}
