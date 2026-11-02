const METERS_PER_KM = 1000;

/** 1km 미만은 m 정수, 이상은 km 소수 둘째 자리 */
export function formatDistance(meters: number): string {
    if (meters < METERS_PER_KM) {
        return `${Math.round(meters)}m`;
    }
    return `${(meters / METERS_PER_KM).toFixed(2)}km`;
}

/** 경사 비율(0.049)을 백분율(4.9%)로 */
export function formatGrade(ratio: number): string {
    return `${(ratio * 100).toFixed(1)}%`;
}

const CLOCK_PATTERN = /T(\d{2}:\d{2})/;

/** ISO 8601 시각의 시:분. 브라우저 시간대와 상관없이 문자열에 적힌 시각 그대로 쓴다. */
export function formatClock(iso: string): string {
    return CLOCK_PATTERN.exec(iso)?.[1] ?? iso;
}
