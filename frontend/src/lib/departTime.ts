// 경로의 출발 시각. 지금이면 실시간 혼잡도를, 시각을 고르면 그 시각의 예측 혼잡도를 쓴다.
// 예측은 한 시간 단위이고 오늘·내일·모레만 있어서(백엔드 route_forecast_days),
// 고를 수 있는 시각도 지금 시부터 모레 23시까지다. 시각은 한국 시각으로 다룬다.

export type DepartTime =
    | { kind: 'now' }
    | {
          kind: 'at';
          /** 오늘부터 며칠 뒤(0 오늘, 1 내일, 2 모레) */
          day: number;
          /** 0 ~ 23시 */
          hour: number;
      };

export const DEPART_NOW: DepartTime = { kind: 'now' };

export const DEPART_DAYS = ['오늘', '내일', '모레'] as const;

const HOURS_PER_DAY = 24;
const KST_OFFSET_MS = 9 * 60 * 60 * 1000;

/** now 의 한국 시각 시(0 ~ 23). */
export function kstHour(now: Date): number {
    return new Date(now.getTime() + KST_OFFSET_MS).getUTCHours();
}

/** 그날 고를 수 있는 시. 오늘은 지금 시부터다(지난 시각은 고를 수 없다). */
export function departHours(day: number, now: Date): number[] {
    const first = day === 0 ? kstHour(now) : 0;
    return Array.from(
        { length: HOURS_PER_DAY - first },
        (_, index) => first + index,
    );
}

/** 고른 시각이 지금 고를 수 있는 범위 안인지. 날이 바뀌어 지난 시각이 되면 false. */
export function isDepartTimeValid(depart: DepartTime, now: Date): boolean {
    if (depart.kind === 'now') {
        return true;
    }
    return (
        Number.isInteger(depart.day) &&
        depart.day >= 0 &&
        depart.day < DEPART_DAYS.length &&
        departHours(depart.day, now).includes(depart.hour)
    );
}

/** 백엔드 depart_at 값. 지금이면 null, 아니면 한국 시각 정시 ISO 문자열(+09:00). */
export function toDepartAt(depart: DepartTime, now: Date): string | null {
    if (depart.kind === 'now') {
        return null;
    }
    const kst = new Date(now.getTime() + KST_OFFSET_MS);
    const date = new Date(
        Date.UTC(
            kst.getUTCFullYear(),
            kst.getUTCMonth(),
            kst.getUTCDate() + depart.day,
        ),
    );
    const yyyy = date.getUTCFullYear();
    const mm = String(date.getUTCMonth() + 1).padStart(2, '0');
    const dd = String(date.getUTCDate()).padStart(2, '0');
    const hh = String(depart.hour).padStart(2, '0');
    return `${yyyy}-${mm}-${dd}T${hh}:00:00+09:00`;
}
